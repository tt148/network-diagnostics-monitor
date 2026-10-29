"""Database setup and session helpers; SQLite is the default backend."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def database_url() -> str:
    """Read the database URL, defaulting to a local SQLite file."""
    return os.getenv("NDM_DATABASE_URL", "sqlite:///./network_diagnostics.db")


def make_engine(url: str | None = None) -> Engine:
    """Create an engine with SQLite foreign-key enforcement enabled."""
    target = url or database_url()
    if target.startswith("sqlite:///") and target != "sqlite:///:memory:":
        db_path = target.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(target, connect_args={"check_same_thread": False} if target.startswith("sqlite") else {})

    if target.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """Create missing tables; safe to call repeatedly."""
    Base.metadata.create_all(engine)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to the provided engine."""
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session and ensure it is closed."""
    session = factory()
    try:
        yield session
    finally:
        session.close()
