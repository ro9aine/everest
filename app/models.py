from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FedresursLookupResultModel(Base):
    __tablename__ = "fedresurs_lookup_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    inn: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    number: Mapped[str] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class KadArbitrLookupResultModel(Base):
    __tablename__ = "kad_arbitr_lookup_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
