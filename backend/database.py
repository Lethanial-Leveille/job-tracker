"""SQLite connection plumbing: engine, session factory, Base, and get_db.

This module owns *how* the app talks to the database. Nothing in here knows
about applications, statuses, or any table yet — it's pure infrastructure.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import get_settings

# The connection URL now comes from config (env-driven): SQLite locally by
# default, Postgres in prod via DATABASE_URL. See config.Settings.database_url.
DATABASE_URL = get_settings().database_url

# check_same_thread=False is a SQLite-only quirk: SQLite forbids sharing one
# connection across threads, and FastAPI serves from a thread pool, so we relax
# it (safe because each request gets its own session via get_db). Postgres
# rejects that arg entirely, so only pass it when the URL is SQLite.
connect_args = (
    {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

# The engine manages the pool of connections. Created once, reused for the life
# of the app.
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# SessionLocal is a factory: call SessionLocal() to get one fresh session,
# which is a single conversation with the DB for one unit of work.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Parent class for every table-model we'll define later.

    SQLAlchemy collects each subclass's table definition here, so Alembic can
    see the full schema. Empty of tables for now — models arrive in piece 2.
    """


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it gets closed.

    FastAPI calls this via Depends() for each request that needs the DB. The
    try/finally makes sure the session closes even if the endpoint raises, so
    connections never leak.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
