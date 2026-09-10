"""The DiscoveredJob model: a posting a robot found, waiting for you to judge it.

The staging half of the discovery feed. A nightly pull reads a public listing of
internship postings, and every job it likes lands HERE — never in `applications`.
You accept one and it becomes a real row; you dismiss it and it never comes back.

Why a separate table rather than an application with status="discovered", which
the status enum already allows. Volume is the whole answer. A few hundred
machine-found postings a week landing in the pipeline would drown the dozen you
actually chose, and every count on the screen — how many you have applied to,
how many are in flight — would quietly start meaning something else. Keeping
them apart means `applications` continues to mean "jobs Lee decided to pursue",
which is the only reason those numbers are worth looking at.

This is the same propose-never-decide shape as models/status_suggestion.py, and
for the same reason: the cost of a missed suggestion is zero, and the cost of a
wrong automatic one is a row you never chose sitting in your pipeline looking
like a decision you made.
"""

import enum
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class DiscoveryState(str, enum.Enum):
    """Where a discovered job is in its short life.

    (str, enum.Enum) so members ARE strings, matching every other enum in this
    schema — convenient for JSON and no surprise about what gets stored.
    """

    pending = "pending"
    accepted = "accepted"
    dismissed = "dismissed"
    # Judged and rejected by the classifier, never shown. Written rather than
    # merely counted, and the reason is cost plus consistency: without a record,
    # every run re-classifies every posting it has already turned down. That is
    # a bill for the same judgement nightly, and because the classifier is not
    # perfectly deterministic, it also means a job rejected last night can
    # appear tonight with no explanation you could give.
    #
    # Caught by running the pull twice in a row: the second run staged seven
    # jobs it should not have.
    filtered = "filtered"


class DiscoveredJob(Base):
    __tablename__ = "discovered_jobs"

    # The constraint that makes the nightly pull safe to run as often as you
    # like. The feed republishes its whole catalogue every day, so without this
    # a second run would re-stage everything already sitting in the inbox, and a
    # job dismissed last week would reappear this week.
    #
    # Scoped per user as well as per source because this app is multi-user now:
    # two people can legitimately hold the same posting, and the dedupe question
    # is always "have I already seen this", never "has anyone".
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source", "external_id", name="uq_discovered_source_id"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Where this came from: "simplify" for the aggregator feed, or the name of
    # an applicant tracking system ("greenhouse", "workday") for a company board
    # we polled directly. A plain VARCHAR rather than an enum, deliberately —
    # adding a source is a code change, where a native Postgres enum would need
    # an ALTER TYPE migration. Same call as Application.role_family.
    source: Mapped[str] = mapped_column(String(32), nullable=False)

    # The company whose board produced this, when it came from one. Null for
    # anything the aggregator found.
    #
    # ondelete="SET NULL" rather than a cascade: removing a company from your
    # watchlist should not silently delete discoveries it already found, some of
    # which you may have accepted. The row survives with its source name intact.
    target_company_id: Mapped[str | None] = mapped_column(
        String(36),
        # Named explicitly. An unnamed constraint cannot be dropped by a
        # downgrade — alembic autogenerates `op.drop_constraint(None, ...)`,
        # which fails outright — so the migration is only reversible if the
        # name exists here.
        ForeignKey(
            "target_companies.id",
            ondelete="SET NULL",
            name="fk_discovered_jobs_target_company",
        ),
        nullable=True,
    )

    # The feed's OWN id for this posting, stored exactly as given. This is what
    # makes re-running the pull idempotent, and it is worth more than any
    # matching we could do ourselves: the feed already knows two of its entries
    # are the same job, where we would be guessing from titles.
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # The posting as the feed describes it. These are what the row shows in the
    # inbox and what get copied onto the application if you accept, so accepting
    # needs no network call and cannot fail.
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    role_or_program: Mapped[str] = mapped_column(String(255), nullable=False)
    posting_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # When the EMPLOYER posted it, per the feed — not when we found it. This is
    # the field worth sorting the inbox by: a job posted this morning and a job
    # posted three weeks ago are worth very different amounts of your attention,
    # and both arrive in the same pull.
    posted_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # The feed entry as received, kept whole. Same JSON-blob call as jd_parsed
    # and fit_report: it is read with the row and never queried across.
    #
    # Worth keeping because the filter is going to be wrong at first. When a
    # posting you wanted gets filtered out, or something irrelevant gets through,
    # this is the only record of what the feed actually said — without it, tuning
    # the filter means guessing at data that is already gone.
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The classifier's verdict on the title, e.g. "Embedded Engineer Intern".
    # Set during staging by the same classify_role_families the backfill uses,
    # which is what decides whether a posting reaches you at all — the feed's own
    # category is far too coarse to make that call, filing firmware roles and RTL
    # roles under one label.
    #
    # Kept on the row rather than recomputed because accepting copies it straight
    # onto the application, so a discovery arrives with role_family already
    # filled in and never needs a second paid call to learn what it is.
    role_family: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Applications this MIGHT already be. Non-empty means "shown to you with a
    # warning", never "hidden".
    #
    # The three-way outcome is the point. A posting whose link matches one you
    # already track is dropped outright and you never see it. A posting that
    # merely looks similar — same employer, near-identical title, different link
    # — is staged WITH the rows it resembles, so the inbox can say "you applied
    # to this on August 3" instead of either hiding a real job or pretending an
    # obvious repeat is new. Same propose-never-decide shape as
    # StatusSuggestion.candidate_application_ids, and the same reason: guessing
    # right about half the time is worse than showing the evidence.
    #
    # A JSON list rather than a join table because it is read whole with the row
    # and discarded when you resolve it. Same call as every other JSON column here.
    possible_application_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # --- What reading the posting found -------------------------------------
    # Filled by the enrichment pass, which fetches and parses each newly staged
    # posting. Everything here is nullable because roughly four in ten ordinary
    # careers sites cannot be read without a browser, and a row that could not
    # be read is still a row worth showing you.

    # The posting text as fetched. Copied onto the application on accept, which
    # is what makes an accepted discovery immediately tailorable instead of
    # needing you to go and paste the description in by hand.
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The parser's output, same shape and same JSON-blob reasoning as
    # Application.jd_parsed. Also copied across on accept.
    jd_parsed: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The graduation-eligibility verdict (schemas via services/eligibility.py):
    # eligible, mismatch, or unclear, with the sentence that decided it.
    #
    # This is the "check compatibility automatically instead of me checking"
    # column. It exists so a posting that wants the Class of 2026 says so in the
    # inbox, before you spend an evening on it.
    eligibility: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # When the posting was last read. Distinct from a boolean because it also
    # answers "is this verdict stale" — the check compares against graduation
    # dates from the master resume, and those change.
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    state: Mapped[DiscoveryState] = mapped_column(
        SqlEnum(DiscoveryState),
        default=DiscoveryState.pending,
        nullable=False,
    )

    # The application this became, once accepted. ondelete="SET NULL" rather
    # than a cascade, matching status_suggestion: deleting the application you
    # created from a discovery should not erase the fact that the feed found it,
    # or this row would go missing and the next pull would stage it all over
    # again as if it were new.
    application_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    # Null until accepted or dismissed. Resolved rows are KEPT, not deleted, for
    # two reasons. The unique constraint above needs them to stay: a deleted
    # dismissal is an invitation for tomorrow's pull to hand you the same job
    # again. And the accept-to-dismiss ratio is the only honest measure of
    # whether the filter is any good — if you are dismissing nine of every ten,
    # the filter is wrong, and nothing else would tell you that.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DiscoveredJob {self.id} {self.organization!r} "
            f"{self.role_or_program!r} state={self.state.value}>"
        )
