"""The DiscoveryRun model: one record per attempt at filling the inbox.

Exists because the pull became asynchronous and asynchronous work that leaves no
trace is work you cannot trust. The webhook now answers immediately and the run
happens afterwards, so without this table there is no way to tell three
situations apart from the outside:

    the feed was quiet and there was genuinely nothing new
    the run is still going
    the run died halfway through and nobody noticed

They all look like an inbox that did not change. A row here says which.

Kept per user rather than globally, like everything else in this schema, and
kept forever: they are tiny, one a night, and the only history of whether the
discovery pipeline actually works.
"""

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class RunState(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    # Finished, but something inside it went wrong — a source that would not
    # answer, or an unhandled error. Distinct from `running` because a failed
    # run is over and a new one may start; distinct from `succeeded` because
    # the inbox may be missing things and you should know that.
    failed = "failed"


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    state: Mapped[RunState] = mapped_column(
        SqlEnum(RunState), default=RunState.running, nullable=False
    )

    # Set when the row is created, which is BEFORE the work starts. That is what
    # makes "is a run already going" answerable, and it is what the 409 on the
    # webhook is checking.
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    # Null while running. The pair of timestamps is also how long a pull takes,
    # which matters now that a slow one is invisible rather than a spinner.
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    staged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enriched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ruled_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Per-source counts, e.g. {"simplify": {"staged": 12, "fetched": 16502}}.
    # A JSON blob rather than columns because the set of sources is expected to
    # grow — direct company boards are next — and each new one would otherwise
    # be a migration. Read whole with the row, never queried across.
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Why it failed, or what went wrong inside a run that otherwise finished.
    # Text rather than a code: the useful version of this is a sentence you can
    # read six weeks later, not an enum you have to look up.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # No cascade: deleting a run must not delete the jobs it found.
    discovered_jobs: Mapped[list["DiscoveredJob"]] = relationship(  # noqa: F821
        "DiscoveredJob",
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryRun {self.id} {self.state.value} "
            f"staged={self.staged} enriched={self.enriched}>"
        )
