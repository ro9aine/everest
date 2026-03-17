from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FedresursLookupResultModel, KadArbitrLookupResultModel


@dataclass(slots=True, frozen=True)
class FedresursLookupPayload:
    inn: str
    case_number: str | None
    latest_date: datetime | None
    source: str
    parsed_at: datetime | None
    status: str
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class KadArbitrLookupPayload:
    case_number: str
    latest_date: datetime | None
    document_name: str | None
    document_title_or_description: str | None
    source: str
    parsed_at: datetime | None
    status: str
    error_message: str | None = None


class FedresursLookupRepository:
    """Repository for idempotent fedresurs result persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, payload: FedresursLookupPayload) -> FedresursLookupResultModel:
        record = self.get_by_inn(payload.inn)
        if record is None:
            record = FedresursLookupResultModel(inn=payload.inn)
            self._session.add(record)

        record.case_number = payload.case_number
        record.latest_date = payload.latest_date
        record.source = payload.source
        record.parsed_at = payload.parsed_at
        record.status = payload.status
        record.error_message = payload.error_message
        self._session.flush()
        return record

    def insert_if_not_exists(self, payload: FedresursLookupPayload) -> FedresursLookupResultModel:
        existing = self.get_by_inn(payload.inn)
        if existing is not None:
            return existing
        return self.upsert(payload)

    def get_by_inn(self, inn: str) -> FedresursLookupResultModel | None:
        stmt = select(FedresursLookupResultModel).where(FedresursLookupResultModel.inn == inn)
        return self._session.scalar(stmt)

    def has_terminal_status(self, inn: str) -> bool:
        record = self.get_by_inn(inn)
        return record is not None and record.status in {"success", "not_found", "permanent_failure"}

    def mark_processing(self, inn: str, *, source: str) -> FedresursLookupResultModel:
        record = self.get_by_inn(inn)
        if record is None:
            record = FedresursLookupResultModel(inn=inn)
            self._session.add(record)

        record.source = source
        record.status = "processing"
        record.error_message = None
        record.parsed_at = None
        self._session.flush()
        return record


class KadArbitrLookupRepository:
    """Repository for idempotent KAD result persistence."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, payload: KadArbitrLookupPayload) -> KadArbitrLookupResultModel:
        record = self.get_by_case_number(payload.case_number)
        if record is None:
            record = KadArbitrLookupResultModel(case_number=payload.case_number)
            self._session.add(record)

        record.latest_date = payload.latest_date
        record.document_name = payload.document_name
        record.document_title_or_description = payload.document_title_or_description
        record.source = payload.source
        record.parsed_at = payload.parsed_at
        record.status = payload.status
        record.error_message = payload.error_message
        self._session.flush()
        return record

    def insert_if_not_exists(self, payload: KadArbitrLookupPayload) -> KadArbitrLookupResultModel:
        existing = self.get_by_case_number(payload.case_number)
        if existing is not None:
            return existing
        return self.upsert(payload)

    def get_by_case_number(self, case_number: str) -> KadArbitrLookupResultModel | None:
        stmt = select(KadArbitrLookupResultModel).where(
            KadArbitrLookupResultModel.case_number == case_number
        )
        return self._session.scalar(stmt)

    def has_terminal_status(self, case_number: str) -> bool:
        record = self.get_by_case_number(case_number)
        return record is not None and record.status in {"success", "not_found", "permanent_failure"}

    def mark_processing(self, case_number: str, *, source: str) -> KadArbitrLookupResultModel:
        record = self.get_by_case_number(case_number)
        if record is None:
            record = KadArbitrLookupResultModel(case_number=case_number)
            self._session.add(record)

        record.source = source
        record.status = "processing"
        record.error_message = None
        record.parsed_at = None
        self._session.flush()
        return record
