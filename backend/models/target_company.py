"""The TargetCompany model: an employer whose job board we poll directly.

The second discovery source. The SimplifyJobs feed is broad and a day or so
behind; this is narrow and immediate, because it reads the system the employer
publishes into rather than a list that reads it later.

Editable in the app rather than hardcoded, which is the point. A hardcoded list
is a deploy every time you change your mind about a company, and the whole value
of this source is that every result is somewhere you actually chose.

The awkward part of the schema is honest rather than accidental. Three of the
five systems identify a board with one string, and two need three. Greenhouse
wants a board token, Lever a company slug, Ashby an org slug — all of which live
in `board`. Workday needs a hostname, a tenant, and a site id. Oracle needs a
hostname and a site number. Keeping them as three nullable columns rather than a
JSON blob means a half-configured company is visible in the table instead of
hidden inside a document, and schemas/company.py rejects the bad combinations at
the API boundary so it fails while you are looking at it rather than at 3am.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

# The systems we can read a whole board from. A plain tuple rather than a
# database enum, for the same reason Application.role_family is a VARCHAR:
# adding a sixth is a code change, where a native Postgres enum would need an
# ALTER TYPE migration.
ATS_NAMES: tuple[str, ...] = ("greenhouse", "lever", "ashby", "workday", "oracle")


class TargetCompany(Base):
    __tablename__ = "target_companies"

    # One company per user per board. The identifier is spread across three
    # columns, so all three are in the constraint — otherwise two Workday sites
    # at the same employer (external vs university hiring, which are genuinely
    # different boards) would collide.
    __table_args__ = (
        UniqueConstraint(
            "user_id", "ats", "host", "board", "site", name="uq_target_board"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # What to call it on screen. Display only — nothing matches on this, because
    # the employer's own name for itself and the name on its board rarely agree.
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    ats: Mapped[str] = mapped_column(String(32), nullable=False)

    # Greenhouse board token, Lever company slug, Ashby org slug, or the Workday
    # tenant. Null for Oracle, which identifies a board by host and site alone.
    board: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Workday and Oracle only: the employer's own hostname.
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Workday site id ("external_experienced"), or Oracle site number ("CX_1001").
    site: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Paused rather than deleted is the common case: a company whose board is
    # noisy this month is one you want back in October, and deleting loses the
    # configuration you worked out.
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Stamped whether the poll worked or not, so "when did we last look" is
    # answerable separately from "did it work".
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Cleared on a successful poll. A company that has been failing quietly for
    # a fortnight is invisible without this — the run finishes, the inbox is
    # thinner than it should be, and nothing says why.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    # No cascade, deliberately: SQLAlchemy nulls the child's foreign key on
    # parent delete, which is exactly what the SET NULL on the constraint says.
    # Declared in the ORM as well as on the constraint because the two layers
    # cover different callers — the constraint holds for psql and migrations,
    # this holds for the app and for the test suite, which runs on SQLite where
    # foreign keys are not enforced at all unless PRAGMA foreign_keys is on.
    # With only the constraint, the behaviour would be untestable here. Same
    # reasoning as Application.status_suggestions.
    #
    # What it protects: jobs this board already found, some of which you may
    # have accepted, must survive you removing the company from the watchlist.
    discovered_jobs: Mapped[list["DiscoveredJob"]] = relationship(  # noqa: F821
        "DiscoveredJob",
    )

    def __repr__(self) -> str:
        return f"<TargetCompany {self.name!r} {self.ats} active={self.active}>"
