"""Database engine and per-request sessions."""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

from aquatrack.api.config import DATABASE_URL

_url = make_url(DATABASE_URL)
_is_sqlite = _url.get_backend_name() == "sqlite"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)


def init_db() -> None:
    """Create tables that don't exist yet. Migrations (alembic) come later."""
    from aquatrack.api import models  # noqa: F401  registers the tables

    if _is_sqlite and _url.database and _url.database != ":memory:":
        Path(_url.database).parent.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
