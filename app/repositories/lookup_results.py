from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FedresursLookupResultModel, KadArbitrLookupResultModel


@dataclass(slots=True, frozen=True)
class FedresursLookupPayload:
    inn: str
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class KadArbitrLookupPayload:
    number: str
    reg_date: datetime | None
    document_name: str | None


class FedresursLookupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(self, payload: FedresursLookupPayload) -> FedresursLookupResultModel:
        record = self._session.scalar(
            select(FedresursLookupResultModel).where(FedresursLookupResultModel.inn == payload.inn)
        )
        if record is None:
            record = FedresursLookupResultModel(
                inn=payload.inn,
                timestamp=payload.timestamp,
            )
            self._session.add(record)
        else:
            record.timestamp = payload.timestamp
        self._session.flush()
        return record

    def list_by_inn(self, inn: str) -> list[FedresursLookupResultModel]:
        stmt = select(FedresursLookupResultModel).where(FedresursLookupResultModel.inn == inn)
        return list(self._session.scalars(stmt))


class KadArbitrLookupRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(self, payload: KadArbitrLookupPayload) -> KadArbitrLookupResultModel:
        record = KadArbitrLookupResultModel(
            number=payload.number,
            reg_date=payload.reg_date,
            document_name=payload.document_name,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def list_by_number(self, number: str) -> list[KadArbitrLookupResultModel]:
        stmt = select(KadArbitrLookupResultModel).where(KadArbitrLookupResultModel.number == number)
        return list(self._session.scalars(stmt))
