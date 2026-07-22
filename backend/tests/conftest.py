"""Shared test fixtures.

A conftest.py is auto-discovered by pytest — any fixture defined here is
available to every test file in this directory without importing it. This one
provides `db`: a fresh, in-memory database for a single test, satisfying the
hard rule that tests never touch the real dev.db.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base

# Importing the model registers the applications table on Base.metadata, so
# create_all below actually builds it. Same reason alembic's env.py imports it.
# The noqa silences "imported but unused" — the import's side effect IS the use.
import models.application  # noqa: F401
import models.resume_version  # noqa: F401


@pytest.fixture
def db() -> Session:
    """Hand a test one clean, isolated database session.

    Everything before `yield` is setup; everything after is teardown that runs
    once the test finishes (pass or fail). Each test gets its own empty DB, so
    tests can't leak state into each other.
    """
    # sqlite:///:memory: is a database that lives in RAM and vanishes when the
    # connection closes. StaticPool forces SQLAlchemy to reuse ONE connection
    # for the whole engine — without it, each new connection would get its own
    # separate empty in-memory DB and the tables we just created would seem to
    # disappear.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
