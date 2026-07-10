"""SQLite connection plumbing: engine, session factory, Base, and get_db.

This module owns *how* the app talks to the database. Nothing in here knows
about applications, statuses, or any table yet — it's pure infrastructure.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Where the SQLite file lives, relative to where we run uvicorn (backend/).
# Hardcoded for v1 on purpose — no secrets or env vars to read yet. This moves
# into config.py the first time we actually need to read a secret (v2 JD parsing).
DATABASE_URL = "sqlite:///./data/dev.db"

# The engine manages the pool of connections to SQLite. Created once, reused
# for the life of the app.
#
# check_same_thread=False: SQLite normally forbids using one connection across
# threads. FastAPI serves requests from a thread pool, so we relax that rule.
# Safe here because SQLAlchemy hands each request its own session (see get_db).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

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
