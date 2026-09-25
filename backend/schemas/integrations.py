"""What MILES sees.

Deliberately NOT the schemas the browser uses. The web UI and a voice assistant
want opposite things: the UI can show a two thousand word job description in a
scrollable panel, while every character MILES receives is pushed through a
model and spoken out loud. So these models are narrow on purpose, and the
exclusions are the design:

  - No `jd_text`. A full posting is thousands of words and there is no spoken
    question whose answer is the raw text.
  - No `jd_parsed` blob. The detail model lifts the handful of fields worth
    saying out of it and leaves the rest.
  - No full `fit_report`. Per requirement verdicts with evidence strings are a
    page to read, not a sentence to hear, so only the counts survive.

The other rule here is that every quantity carries its unit in its NAME.
`days_until_deadline` rather than `deadline`, `days_since_applied` rather than
a timestamp to subtract. This is not style. A model handed a bare number or a
bare date assigns it a meaning, and the assistant this feeds already shipped a
bug of exactly that shape: an Oura score out of a hundred was read as a hundred
minutes and spoken as a sleep duration. Dates are still included beside the day
counts for anything that wants to be precise, but nothing has to do arithmetic
to answer "is that soon".
"""

from datetime import date, datetime

from pydantic import BaseModel

from models.application import ApplicationStatus, Priority
from models.status_suggestion import SuggestionState
from schemas.roles import RoleFamily


class MilesApplication(BaseModel):
    """One application, shaped for a sentence.

    Doubles as the row type for the summary's deadline and stale lists rather
    than each of those getting a near identical model of its own. They are the
    same thing seen through different filters.
    """

    id: str
    organization: str
    role: str
    status: ApplicationStatus
    priority: Priority
    posting_url: str
    role_family: RoleFamily | None = None

    # Kept beside each other on purpose: the date for anything that wants to be
    # exact, the count for anything that wants to answer "is that soon".
    # Negative days_until_deadline means the deadline has passed.
    deadline: date | None = None
    days_until_deadline: int | None = None

    # Null when the row has never reached `applied`, which is different from
    # applied today. Null means "not yet", not zero.
    applied_at: datetime | None = None
    days_since_applied: int | None = None

    # How long this row has sat at its current status. This is the number that
    # makes "Stripe has been silent for 24 days" sayable, and it is the one
    # thing here you would never think to ask for.
    days_since_last_change: int | None = None


class MilesApplicationDetail(MilesApplication):
    """One application, opened up.

    Everything on the list model plus the few fields that only matter once you
    have picked a row. Still no posting text: if you want to know what a job
    asks for, `key_requirements` is the answer that fits in a sentence, and it
    is what the parser already extracted.
    """

    location: str | None = None
    salary: str | None = None
    summary: str | None = None
    key_requirements: list[str] = []
    notes: str | None = None

    # The fit check reduced to its scoreboard. Null across the board means no
    # fit report has been run for this row, which is different from a bad score.
    requirements_met: int | None = None
    requirements_partial: int | None = None
    requirements_total: int | None = None


class MilesDiscovered(BaseModel):
    """One staged job waiting in the discovery inbox.

    `fit_score` is null when the posting could not be read or listed no
    requirements. Unknown, not zero, and it should not be spoken as a zero.
    """

    id: str
    organization: str
    role: str
    posting_url: str
    source: str
    location: str | None = None
    posted_at: date | None = None
    role_family: str | None = None
    fit_score: int | None = None

    # Non-empty means Prowl thinks this might already be in the pipeline, so
    # accepting it would file a duplicate. Worth saying out loud before acting.
    possible_duplicate_of: list[str] = []


class MilesSuggestion(BaseModel):
    """A status change waiting on you, with enough context to answer by voice.

    The web UI can afford a bare count because the list is one click away. A
    spoken count is a dead end: "you have three suggestions" sends you to a
    laptop, while "Google moved to rejected" is something you can respond to
    where you are standing. So the organization is resolved here rather than
    left as an application_id.

    `organization` is null for a suggestion that matched no application, or
    matched several. Those are the ones that genuinely need a screen.
    """

    id: str
    suggested_status: ApplicationStatus
    reason: str
    state: SuggestionState
    created_at: datetime
    days_waiting: int
    application_id: str | None = None
    organization: str | None = None
    needs_a_screen: bool = False


class MilesSummary(BaseModel):
    """The whole search in one object, built to be read aloud.

    Shaped for the morning brief rather than for arbitrary questions, because
    the brief is the half of this integration that is actually worth having:
    the point of a job tracker attached to an assistant is the thing you forgot
    to check, not the thing you remembered to ask.

    Every list here is already filtered and already sorted, and the counting
    happens in Python. Handing a model the raw pipeline and asking it to count
    is how you get a confident wrong number.
    """

    active_count: int
    counts_by_status: dict[str, int] = {}
    upcoming_deadlines: list[MilesApplication] = []

    # Deadlines that have already passed on rows you never applied to. Kept
    # apart from upcoming_deadlines rather than folded in as negative days,
    # because they are a different sentence: one is "this is coming up", the
    # other is "this got away from you". A passed deadline on a row you DID
    # apply to is not here at all, since applying in time is the whole point.
    overdue: list[MilesApplication] = []
    stale: list[MilesApplication] = []
    pending_suggestions: list[MilesSuggestion] = []
    discovered_waiting: int = 0
