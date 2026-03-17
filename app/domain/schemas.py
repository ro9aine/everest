from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class FedresursResult:
    """Normalized bankruptcy lookup result for a single INN."""

    inn: str
    person_guid: str
    bankruptcy_case_number: str
    latest_date: datetime | None
    raw_person_payload: dict
    raw_bankruptcy_payload: dict


@dataclass(slots=True, frozen=True)
class KadArbitrDocument:
    """Normalized document extracted from a KAD case card."""

    document_date: datetime | None
    document_name: str | None
    document_title: str | None


@dataclass(slots=True, frozen=True)
class KadArbitrResult:
    """Normalized KAD lookup result for a single case number."""

    case_number: str
    card_id: str
    card_url: str
    latest_date: datetime | None
    latest_document_name: str | None
    latest_document_title: str | None
    documents: tuple[KadArbitrDocument, ...]
    raw_search_payload: dict
    raw_card_payload: dict
