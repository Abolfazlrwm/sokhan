"""Archive search over normalized transcript text.

Both Postgres and SQLite search the same `jobs.text_normalized` column that
the pipeline fills with `normalize_persian(text)`. Postgres additionally gets
a pg_trgm GIN index so substring queries stay fast on large archives; SQLite
(development, CI) falls back to plain ILIKE. See docs/adr/0001 and
docs/architecture.md.
"""

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from sokhan.core.persian import normalize_persian
from sokhan.models import Job


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_jobs(session: Session, user_id: str, query: str, limit: int = 50) -> list[Job]:
    """Return the user's jobs matching the query in text or filename."""
    normalized = normalize_persian(query).strip()
    stmt = select(Job).where(Job.user_id == user_id)
    if normalized:
        like = _like_pattern(normalized)
        conditions: list[ColumnElement[bool]] = [
            Job.text_normalized.ilike(like, escape="\\"),
            Job.filename.ilike(like, escape="\\"),
        ]
        if session.get_bind().dialect.name == "postgresql":
            # Trigram similarity tolerates small typos on Postgres archives.
            conditions.append(func.similarity(Job.text_normalized, normalized) > 0)
        stmt = stmt.where(or_(*conditions))
    return list(session.scalars(stmt.order_by(Job.created_at.desc()).limit(limit)))


def ensure_postgres_search_objects(engine: Engine) -> None:
    """Create the pg_trgm extension and GIN index (idempotent)."""
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_jobs_text_normalized_trgm "
                "ON jobs USING gin (text_normalized gin_trgm_ops)"
            )
        )
