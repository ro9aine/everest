from __future__ import annotations

from collections import defaultdict
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.adapters import BlockedByUpstreamError, NotFoundError, TemporaryNetworkError
from app.adapters.dto import FedresursResult, KadArbitrDocument, KadArbitrResult
from app.config import ExecutionSettings
from app.db import create_db_engine, create_session_factory, init_db
from app.services import BatchProcessingService, BatchSource


@dataclass(slots=True, frozen=True)
class FakeInputRow:
    row_number: int
    value: str


@dataclass(slots=True, frozen=True)
class FakeInputBatch:
    rows: tuple[FakeInputRow, ...]
    skipped_empty: int


class FakeExcelReader:
    def __init__(self, batch: FakeInputBatch) -> None:
        self.batch = batch

    def read(self, path: str, *, sheet: str | None = None, column: str):
        return self.batch


class FakeFedresursAdapter:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls = defaultdict(int)
        self.closed = False

    def get_bankruptcy_info(self, inn: str) -> FedresursResult:
        self.calls[inn] += 1
        outcome = self.outcomes[inn]
        if callable(outcome):
            outcome = outcome(self.calls[inn])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


class FakeKadAdapter:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls = defaultdict(int)
        self.closed = False

    def get_case_documents(self, case_number: str) -> KadArbitrResult:
        self.calls[case_number] += 1
        outcome = self.outcomes[case_number]
        if callable(outcome):
            outcome = outcome(self.calls[case_number])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def close(self) -> None:
        self.closed = True


def build_session_factory(tmp_path: Path | None = None):
    database_url = "sqlite:///:memory:" if tmp_path is None else f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_db_engine(database_url)
    init_db(engine)
    return create_session_factory(engine)


def test_batch_service_processes_fedresurs_rows_and_persists_outcomes() -> None:
    session_factory = build_session_factory()
    adapter = FakeFedresursAdapter(
        {
            "123": FedresursResult(
                inn="123",
                person_guid="guid-1",
                bankruptcy_case_number="A40-1/2024",
                latest_date=datetime(2024, 1, 10, 10, 0, 0),
                raw_person_payload={},
                raw_bankruptcy_payload={},
            ),
            "456": NotFoundError("missing"),
            "789": TemporaryNetworkError("retry later"),
        }
    )
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(
                rows=(
                    FakeInputRow(2, "123"),
                    FakeInputRow(3, "456"),
                    FakeInputRow(4, "789"),
                ),
                skipped_empty=1,
            )
        ),
        fedresurs_adapter=adapter,
        execution_settings=ExecutionSettings(retry_attempts=1),
        logger=logging.getLogger("test.batch.fedresurs"),
    )

    summary = service.run(
        source=BatchSource.FEDRESURS,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="INN",
    )

    assert summary.total == 3
    assert summary.success == 1
    assert summary.not_found == 1
    assert summary.temporary_failures == 1
    assert summary.permanent_failures == 0
    assert summary.skipped == 1
    assert adapter.closed is True


def test_batch_service_resume_skips_terminal_kad_rows() -> None:
    session_factory = build_session_factory()
    first_adapter = FakeKadAdapter(
        {
            "A40-1/2024": KadArbitrResult(
                case_number="A40-1/2024",
                card_id="card-1",
                card_url="https://kad.arbitr.ru/Card/card-1",
                latest_date=datetime(2024, 2, 10, 10, 0, 0),
                latest_document_name="Order",
                latest_document_title="Initial order",
                documents=(
                    KadArbitrDocument(
                        document_date=datetime(2024, 2, 10, 10, 0, 0),
                        document_name="Order",
                        document_title="Initial order",
                    ),
                ),
                raw_search_payload={},
                raw_card_payload={},
            )
        }
    )
    second_adapter = FakeKadAdapter({"A40-1/2024": TemporaryNetworkError("should not be called")})
    first_service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(rows=(FakeInputRow(2, "A40-1/2024"),), skipped_empty=0)
        ),
        kad_adapter=first_adapter,
        logger=logging.getLogger("test.batch.kad.first"),
    )
    second_service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(rows=(FakeInputRow(2, "A40-1/2024"),), skipped_empty=0)
        ),
        kad_adapter=second_adapter,
        logger=logging.getLogger("test.batch.kad.second"),
    )

    first_summary = first_service.run(
        source=BatchSource.KAD,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="CASE",
        resume=False,
    )
    second_summary = second_service.run(
        source=BatchSource.KAD,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="CASE",
        resume=True,
    )

    assert first_summary.success == 1
    assert second_summary.total == 1
    assert second_summary.skipped == 1
    assert second_summary.success == 0
    assert second_adapter.calls["A40-1/2024"] == 0


def test_batch_service_retries_transient_failures_then_succeeds() -> None:
    session_factory = build_session_factory()
    adapter = FakeFedresursAdapter(
        {
            "123": lambda attempt: TemporaryNetworkError("retry") if attempt < 3 else FedresursResult(
                inn="123",
                person_guid="guid-1",
                bankruptcy_case_number="A40-1/2024",
                latest_date=datetime(2024, 1, 10, 10, 0, 0),
                raw_person_payload={},
                raw_bankruptcy_payload={},
            )
        }
    )
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(FakeInputBatch(rows=(FakeInputRow(2, "123"),), skipped_empty=0)),
        fedresurs_adapter=adapter,
        execution_settings=ExecutionSettings(
            retry_attempts=3,
            retry_backoff_base_seconds=0.0,
            retry_backoff_multiplier=1.0,
        ),
        logger=logging.getLogger("test.batch.retry"),
    )

    summary = service.run(
        source=BatchSource.FEDRESURS,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="INN",
    )

    assert summary.success == 1
    assert adapter.calls["123"] == 3


def test_batch_service_marks_anti_bot_as_permanent_failure() -> None:
    session_factory = build_session_factory()
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(FakeInputBatch(rows=(FakeInputRow(2, "A40-1/2024"),), skipped_empty=0)),
        kad_adapter=FakeKadAdapter({"A40-1/2024": BlockedByUpstreamError("blocked")}),
        execution_settings=ExecutionSettings(retry_attempts=3),
        logger=logging.getLogger("test.batch.blocked"),
    )

    summary = service.run(
        source=BatchSource.KAD,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="CASE",
    )

    assert summary.permanent_failures == 1


def test_batch_service_uses_bounded_concurrency(tmp_path) -> None:
    session_factory = build_session_factory(tmp_path)
    adapter = FakeFedresursAdapter(
        {
            "123": FedresursResult(
                inn="123",
                person_guid="guid-1",
                bankruptcy_case_number="A40-1/2024",
                latest_date=datetime(2024, 1, 10, 10, 0, 0),
                raw_person_payload={},
                raw_bankruptcy_payload={},
            ),
            "456": FedresursResult(
                inn="456",
                person_guid="guid-2",
                bankruptcy_case_number="A40-2/2024",
                latest_date=datetime(2024, 1, 11, 10, 0, 0),
                raw_person_payload={},
                raw_bankruptcy_payload={},
            ),
        }
    )
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(rows=(FakeInputRow(2, "123"), FakeInputRow(3, "456")), skipped_empty=0)
        ),
        fedresurs_adapter=adapter,
        execution_settings=ExecutionSettings(worker_count=2, retry_attempts=1),
        logger=logging.getLogger("test.batch.concurrent"),
    )

    summary = service.run(
        source=BatchSource.FEDRESURS,
        input_path="ignored.xlsx",
        sheet="Sheet1",
        column="INN",
    )

    assert summary.success == 2
