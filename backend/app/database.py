"""SQLAlchemy engine, session factory and declarative base.

Deliberately database-agnostic. SQLite gets two extra pragmas because its
defaults are wrong for our access pattern:

  * ``check_same_thread=False``  -- FastAPI serves requests on a threadpool and
    the simulator ticks on the event loop; without this SQLite refuses the
    cross-thread connection.
  * ``PRAGMA foreign_keys=ON``   -- SQLite does NOT enforce foreign keys by
    default. Without this our FK constraints would be decorative and the
    tenant-isolation guarantees would rest on application code alone.
"""

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args: dict = {}
if settings.is_sqlite:
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.SQL_ECHO,
    connect_args=connect_args,
    pool_pre_ping=True,
)


if settings.is_sqlite:

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets the simulator write while the API reads, instead of blocking.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
