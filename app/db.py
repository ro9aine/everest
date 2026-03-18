from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    """Shared declarative base for ORM models."""

    metadata = MetaData()


def create_db_engine(database_url: str | None = None, *, echo: bool = False) -> Engine:
    settings = Settings.from_env()
    target_url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if target_url.startswith("sqlite") else {}
    return create_engine(target_url, echo=echo, future=True, connect_args=connect_args)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
