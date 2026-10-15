"""Database engine and sessions. SQLite file at data/twin.db unless DATABASE_URL says otherwise."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from config.settings import get_settings
from src.db import models  # noqa: F401  (registers the tables)

_url = get_settings().database_url
if _url.startswith("sqlite:///"):
    Path(_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _url,
    connect_args={"check_same_thread": False} if _url.startswith("sqlite") else {},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def drop_all() -> None:
    SQLModel.metadata.drop_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with Session(engine) as session:
        yield session


def is_empty() -> bool:
    with Session(engine) as session:
        return session.exec(select(models.User)).first() is None
