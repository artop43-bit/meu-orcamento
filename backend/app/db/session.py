from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_database_url = get_settings().database_url
_is_sqlite = _database_url.startswith("sqlite")
engine = create_engine(
    _database_url,
    pool_pre_ping=True,
    connect_args={"timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=30000")
        if ":memory:" not in _database_url and "mode=memory" not in _database_url:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
