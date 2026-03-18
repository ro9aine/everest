from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.db import create_db_engine, create_session_factory, init_db
from app.repositories.lookup_results import FedresursLookupRepository, KadArbitrLookupRepository
from app.services import BatchProcessingService


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

    def read(self, path: str, *, sheet: str | None = None, column: str = ""):
        return self.batch


class FakeFedresursParser:
    def __init__(self, persons_payload: dict[str, dict], bankruptcy_payload: dict[str, dict]) -> None:
        self.persons_payload = persons_payload
        self.bankruptcy_payload = bankruptcy_payload
        self.session = None

    def find_persons(self, inn: str) -> dict:
        return self.persons_payload[inn]

    def get_bankruptcy_info(self, guid: str) -> dict:
        return self.bankruptcy_payload[guid]


class FakeKadParser:
    def __init__(self, search_payload: dict[str, dict], card_payload: dict[str, dict]) -> None:
        self.search_payload = search_payload
        self.card_payload = card_payload
        self.session = None

    def search_by_number(self, number: str) -> dict:
        return self.search_payload[number]

    def get_card_info(self, card: dict[str, str]) -> dict:
        return self.card_payload[card["CardId"]]


def build_session_factory(tmp_path: Path | None = None):
    database_url = "sqlite:///:memory:" if tmp_path is None else f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_db_engine(database_url)
    init_db(engine)
    return create_session_factory(engine)


def test_batch_service_processes_inn_and_persists_both_results() -> None:
    session_factory = build_session_factory()
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(rows=(FakeInputRow(2, "1234567890"),), skipped_empty=1)
        ),
        fedresurs_parser=FakeFedresursParser(
            persons_payload={
                "1234567890": {
                    "pageData": [
                        {
                            "guid": "guid-1",
                            "inn": "1234567890",
                        }
                    ]
                }
            },
            bankruptcy_payload={
                "guid-1": {
                    "legalCases": [
                        {
                            "number": "A40-1/2024",
                        }
                    ]
                }
            },
        ),
        kad_parser=FakeKadParser(
            search_payload={
                "A40-1/2024": {
                    "Result": {
                        "Items": [
                            {
                                "CaseNumber": "A40-1/2024",
                                "CardId": "card-1",
                                "CardUrl": "https://kad.arbitr.ru/Card/card-1",
                            }
                        ]
                    }
                }
            },
            card_payload={
                "card-1": {
                    "CardId": "card-1",
                    "CardUrl": "https://kad.arbitr.ru/Card/card-1",
                    "LatestDocumentDate": datetime(2024, 2, 10, 10, 0, 0),
                    "ResultText": "Order",
                }
            },
        ),
        logger=logging.getLogger("test.batch.pipeline"),
    )

    summary = service.run(input_path="ignored.xlsx", column="INN")

    assert summary.total == 1
    assert summary.success == 1
    assert summary.failed == 0
    assert summary.skipped == 1

    with session_factory() as session:
        fedresurs_rows = FedresursLookupRepository(session).list_by_inn("1234567890")
        kad_rows = KadArbitrLookupRepository(session).list_by_number("A40-1/2024")

    assert len(fedresurs_rows) == 1
    assert fedresurs_rows[0].inn == "1234567890"
    assert fedresurs_rows[0].number == "A40-1/2024"
    assert fedresurs_rows[0].timestamp is not None

    assert len(kad_rows) == 1
    assert kad_rows[0].number == "A40-1/2024"
    assert kad_rows[0].timestamp == datetime(2024, 2, 10, 10, 0, 0)
    assert kad_rows[0].document_name == "Order"


def test_batch_service_counts_failures_when_fedresurs_has_no_persons() -> None:
    session_factory = build_session_factory()
    service = BatchProcessingService(
        session_factory,
        excel_reader=FakeExcelReader(
            FakeInputBatch(rows=(FakeInputRow(2, "1234567890"),), skipped_empty=0)
        ),
        fedresurs_parser=FakeFedresursParser(
            persons_payload={"1234567890": {"pageData": []}},
            bankruptcy_payload={},
        ),
        kad_parser=FakeKadParser(search_payload={}, card_payload={}),
        logger=logging.getLogger("test.batch.failure"),
    )

    summary = service.run(input_path="ignored.xlsx", column="INN")

    assert summary.total == 1
    assert summary.success == 0
    assert summary.failed == 1
    assert summary.skipped == 0

    with session_factory() as session:
        fedresurs_rows = FedresursLookupRepository(session).list_by_inn("1234567890")
        kad_rows = KadArbitrLookupRepository(session).list_by_number("A40-1/2024")

    assert fedresurs_rows == []
    assert kad_rows == []
