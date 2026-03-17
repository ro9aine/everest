from __future__ import annotations

from datetime import datetime

from app.db import create_db_engine, create_session_factory, init_db
from app.models import FedresursLookupResultModel, KadArbitrLookupResultModel
from app.repositories.lookup_results import (
    FedresursLookupPayload,
    FedresursLookupRepository,
    KadArbitrLookupPayload,
    KadArbitrLookupRepository,
)


def test_init_db_creates_tables() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)

    table_names = set(FedresursLookupResultModel.metadata.tables)

    assert "fedresurs_lookup_results" in table_names
    assert "kad_arbitr_lookup_results" in table_names


def test_fedresurs_repository_upsert_updates_existing_row() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = FedresursLookupRepository(session)
        repository.upsert(
            FedresursLookupPayload(
                inn="1234567890",
                case_number="A40-1/2024",
                latest_date=datetime(2024, 1, 10, 9, 0, 0),
                source="fedresurs",
                parsed_at=datetime(2024, 1, 10, 9, 5, 0),
                status="success",
            )
        )
        repository.upsert(
            FedresursLookupPayload(
                inn="1234567890",
                case_number="A40-2/2024",
                latest_date=datetime(2024, 1, 11, 9, 0, 0),
                source="fedresurs",
                parsed_at=datetime(2024, 1, 11, 9, 5, 0),
                status="success",
            )
        )
        session.commit()

        row = repository.get_by_inn("1234567890")

    assert row is not None
    assert row.case_number == "A40-2/2024"
    assert row.status == "success"


def test_kad_repository_insert_if_not_exists_prevents_duplicate_row() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = KadArbitrLookupRepository(session)
        first = repository.insert_if_not_exists(
            KadArbitrLookupPayload(
                case_number="A40-1/2024",
                latest_date=datetime(2024, 2, 10, 10, 0, 0),
                document_name="Order",
                document_title_or_description="Initial order",
                source="kad.arbitr",
                parsed_at=datetime(2024, 2, 10, 10, 5, 0),
                status="success",
            )
        )
        second = repository.insert_if_not_exists(
            KadArbitrLookupPayload(
                case_number="A40-1/2024",
                latest_date=datetime(2024, 2, 11, 10, 0, 0),
                document_name="Notice",
                document_title_or_description="Should not overwrite",
                source="kad.arbitr",
                parsed_at=datetime(2024, 2, 11, 10, 5, 0),
                status="success",
            )
        )
        session.commit()

        row = repository.get_by_case_number("A40-1/2024")

    assert row is not None
    assert first.id == second.id
    assert row.document_name == "Order"
    assert row.document_title_or_description == "Initial order"
