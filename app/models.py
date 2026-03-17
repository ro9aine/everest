from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FedresursLookupResultModel(Base):
    """Persistent result of a fedresurs lookup keyed by INN."""

    __tablename__ = "fedresurs_lookup_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    inn: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    case_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    latest_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="fedresurs", server_default="fedresurs")
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        server_default=func.now(),
    )


class KadArbitrLookupResultModel(Base):
    """Persistent result of a KAD lookup keyed by case number."""

    __tablename__ = "kad_arbitr_lookup_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    latest_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_title_or_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="kad.arbitr", server_default="kad.arbitr")
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        server_default=func.now(),
    )
