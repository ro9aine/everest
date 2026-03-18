from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.excel import ExcelInputReader
from app.parsers.fedresurs import FedResursParser
from app.parsers.kad import KadParser
from app.parsers.retrying import RetryPolicy, RetryingFedResursParser, RetryingKadParser
from app.repositories.lookup_results import (
    FedresursLookupPayload,
    FedresursLookupRepository,
    KadArbitrLookupPayload,
    KadArbitrLookupRepository,
)


@dataclass(slots=True)
class BatchProcessingSummary:
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0


class BatchProcessingService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        excel_reader: ExcelInputReader | None = None,
        fedresurs_parser: FedResursParser | None = None,
        kad_parser: KadParser | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._excel_reader = excel_reader or ExcelInputReader()
        self._logger = logger or logging.getLogger(__name__)
        settings = Settings.from_env()
        retry_policy = RetryPolicy(
            attempts=settings.retry.attempts,
            backoff_seconds=settings.retry.backoff_seconds,
            backoff_multiplier=settings.retry.backoff_multiplier,
        )
        self._fedresurs_parser = fedresurs_parser or RetryingFedResursParser(
            FedResursParser(),
            retry_policy=retry_policy,
        )
        self._kad_parser = kad_parser or RetryingKadParser(
            KadParser(),
            retry_policy=retry_policy,
        )

    def run(self, *, input_path: str, column: str) -> BatchProcessingSummary:
        input_batch = self._excel_reader.read(input_path, column=column)
        summary = BatchProcessingSummary(
            total=len(input_batch.rows),
            skipped=input_batch.skipped_empty,
        )

        try:
            for row in input_batch.rows:
                try:
                    self._process_row(row.value)
                except Exception as exc:
                    summary.failed += 1
                    self._logger.error(
                        "row=%s value=%s status=failed error=%s",
                        row.row_number,
                        row.value,
                        exc,
                    )
                else:
                    summary.success += 1
                    self._logger.info("row=%s value=%s status=success", row.row_number, row.value)
        finally:
            self._close_session(self._fedresurs_parser)
            self._close_session(self._kad_parser)

        return summary

    def _process_row(self, inn: str) -> None:
        person = self._get_first_person(inn)
        number = self._get_bankruptcy_number(person)
        self._save_fedresurs_result(inn=inn)

        card_info = self._get_kad_card_info(number)
        self._save_kad_result(
            number=number,
            reg_date=card_info.get("RegDate"),
            document_name=card_info.get("ResultText"),
        )

    def _get_first_person(self, inn: str) -> dict:
        persons_result = self._fedresurs_parser.find_persons(inn)
        page_data = persons_result.get("pageData")
        if not isinstance(page_data, list) or not page_data or not isinstance(page_data[0], dict):
            raise ValueError(f"Fedresurs returned no persons for INN '{inn}'")
        return page_data[0]

    def _get_bankruptcy_number(self, person: dict) -> str:
        guid = person.get("guid")
        if not isinstance(guid, str) or not guid.strip():
            raise ValueError("Fedresurs person payload is missing guid")

        bankruptcy_result = self._fedresurs_parser.get_bankruptcy_info(guid.strip())
        legal_cases = bankruptcy_result.get("legalCases")
        if not isinstance(legal_cases, list) or not legal_cases or not isinstance(legal_cases[0], dict):
            raise ValueError("Fedresurs bankruptcy payload is missing legalCases")

        number = legal_cases[0].get("number")
        if not isinstance(number, str) or not number.strip():
            raise ValueError("Fedresurs bankruptcy payload is missing legalCases[0].number")
        return number.strip()

    def _get_kad_card_info(self, number: str) -> dict:
        search_result = self._kad_parser.search_by_number(number)
        items = search_result.get("Result", {}).get("Items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"KAD returned no cases for number '{number}'")
        if not isinstance(items[0], dict):
            raise ValueError("KAD search payload contains an invalid first item")
        return self._kad_parser.get_card_info(items[0])

    def _save_fedresurs_result(self, *, inn: str) -> None:
        with self._session_factory() as session:
            repository = FedresursLookupRepository(session)
            repository.insert(
                FedresursLookupPayload(
                    inn=inn,
                    timestamp=datetime.utcnow(),
                )
            )
            session.commit()

    def _save_kad_result(
        self,
        *,
        number: str,
        reg_date: datetime | None,
        document_name: str | None,
    ) -> None:
        with self._session_factory() as session:
            repository = KadArbitrLookupRepository(session)
            repository.insert(
                KadArbitrLookupPayload(
                    number=number,
                    reg_date=reg_date,
                    document_name=document_name,
                )
            )
            session.commit()

    @staticmethod
    def _close_session(parser: object) -> None:
        session = getattr(parser, "session", None)
        close = getattr(session, "close", None)
        if callable(close):
            close()
