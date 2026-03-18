from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

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


def test_fedresurs_repository_enforces_unique_inn() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = FedresursLookupRepository(session)
        repository.insert(
            FedresursLookupPayload(
                inn="1234567890",
                number="A40-1/2024",
                timestamp=datetime(2024, 1, 10, 9, 5, 0),
            )
        )
        with pytest.raises(IntegrityError):
            repository.insert(
                FedresursLookupPayload(
                    inn="1234567890",
                    number="A40-2/2024",
                    timestamp=datetime(2024, 1, 11, 9, 5, 0),
                )
            )

        session.rollback()
        rows = repository.list_by_inn("1234567890")

    assert len(rows) == 0


def test_kad_repository_enforces_unique_number() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    init_db(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        repository = KadArbitrLookupRepository(session)
        repository.insert(
            KadArbitrLookupPayload(
                number="A40-1/2024",
                timestamp=datetime(2024, 2, 10, 10, 0, 0),
                document_name="Order",
            )
        )
        with pytest.raises(IntegrityError):
            repository.insert(
                KadArbitrLookupPayload(
                    number="A40-1/2024",
                    timestamp=datetime(2024, 2, 11, 10, 0, 0),
                    document_name="Notice",
                )
            )

        session.rollback()
        rows = repository.list_by_number("A40-1/2024")

    assert len(rows) == 0
