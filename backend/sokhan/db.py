"""Database engine and session management.

The engine is configured lazily from settings, so tests can point it at a
throwaway SQLite database with ``db.configure(...)`` before the application
starts. A Postgres connection is expected in real deployments; SQLite keeps
development and CI simple.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure(database_url: str | None = None) -> Engine:
    """Create (or keep) the global engine. Returns the active engine."""
    global _engine, _session_factory
    if database_url is None and _engine is not None:
        # Already configured (e.g. by tests); keep that engine.
        return _engine
    url = database_url or _default_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    _engine = create_engine(url, connect_args=connect_args, future=True)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def _default_url() -> str:
    from sokhan.config import get_settings

    return get_settings().database_url


def get_engine() -> Engine:
    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure()
    assert _session_factory is not None
    return _session_factory


def create_all() -> None:
    """Create all tables if missing, plus Postgres-specific search helpers."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        from sokhan.search import ensure_postgres_search_objects

        ensure_postgres_search_objects(engine)


def reset() -> None:
    """Forget the cached engine; used by tests to isolate state."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session context for worker and CLI code with commit/rollback."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
