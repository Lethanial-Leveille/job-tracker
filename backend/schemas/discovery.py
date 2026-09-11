"""Shapes for the discovery feed: what a listing looks like coming in, and what
a staged job looks like going back out to the UI.

Two very different kinds of model live here on purpose. FeedListing describes
data we do not control and cannot correct — a public file republished daily by
someone else. Everything below it describes our own rows.
"""

from datetime import UTC, date, datetime

from pydantic import BaseModel

from models.discovered_job import DiscoveryState
from models.discovery_run import RunState


class FeedListing(BaseModel):
    """One entry from the discovery feed, as published.

    EVERY field has a default, including ones that are always present today.
    That is not laziness, it is the same rule CLAUDE.md sets for stored JSON
    blobs, applied to an external feed for the same reason: this validates
    sixteen thousand entries written by someone else, and one entry missing one
    field must not raise and take the entire nightly pull down with it. A
    listing that arrives without a url or a title is simply dropped by the
    filter, which is a much better outcome than an exception.

    Field names mirror the feed's own, rather than being renamed to match our
    columns. Mapping happens once, explicitly, when a listing becomes a row —
    renaming here would hide which side of that boundary a mistake came from.
    """

    id: str = ""
    company_name: str = ""
    title: str = ""
    url: str = ""
    source: str = ""
    category: str = ""
    active: bool = False
    is_visible: bool = True
    # Unix seconds. Kept raw rather than parsed to a date by a validator so that
    # an unparseable value is a filtered-out listing rather than a failed pull.
    date_posted: float | None = None
    terms: list[str] = []
    locations: list[str] = []
    degrees: list[str] = []
    sponsorship: str = ""

    def posted_on(self) -> date | None:
        """The posted timestamp as a date, or None if it is missing or unusable."""
        if self.date_posted is None:
            return None
        try:
            return datetime.fromtimestamp(self.date_posted, tz=UTC).date()
        except (OverflowError, OSError, ValueError):
            return None


class StageCandidate(BaseModel):
    """One job on its way into the inbox, from any source.

    The neutral shape that lets the aggregator feed and a company's own board
    share a staging path. Everything downstream of here — deduplication,
    classification, writing the row — must treat the two identically, and the
    only way to guarantee that is for them to arrive identical.

    What the two sources do NOT share is the step before this. The feed carries
    a term, a degree list and a category, so most of its entries are discarded
    for free; a board carries none of that, so its postings go straight to the
    classifier. That asymmetry belongs upstream, not here.
    """

    source: str
    external_id: str
    organization: str
    role_or_program: str
    posting_url: str
    location: str | None = None
    posted_at: date | None = None
    target_company_id: str | None = None
    raw: dict | None = None


class DiscoveredJobRead(BaseModel):
    """A staged job as the UI sees it."""

    id: str
    source: str
    organization: str
    role_or_program: str
    posting_url: str
    location: str | None = None
    posted_at: date | None = None
    state: DiscoveryState
    # Which company's board produced this, when it came from one. Null for
    # anything the aggregator found.
    target_company_id: str | None = None
    role_family: str | None = None
    # Applications this might already be. Non-empty means the inbox shows a
    # "you may already have this" note rather than hiding the row.
    possible_application_ids: list[str] | None = None
    # What reading the posting found. None means it has not been read, or could
    # not be — distinct from a verdict of "unclear", which means it WAS read and
    # said nothing about graduation timing.
    eligibility: dict | None = None
    # How well your resume answers this posting's requirements, 0-100. Null when
    # the posting could not be read or stated no requirements — unknown rather
    # than zero, and sorted as such.
    fit_score: int | None = None
    fit_report: dict | None = None
    # The pull that found it, so the inbox can mark what is new since last time.
    run_id: str | None = None
    enriched_at: datetime | None = None
    application_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PullResult(BaseModel):
    """What one run of the feed pull did.

    `dropped` is the part worth having. The filter is going to be wrong at
    first, and a pull that reports only "staged 4" gives you no way to tell a
    quiet night from a filter that is silently discarding everything. Counting
    by reason turns that into something you can read: "1,300 wrong term, 900
    wrong category" is a filter working, and "3,500 wrong category" is a filter
    that has stopped recognizing the feed's own labels.
    """

    fetched: int = 0
    kept: int = 0
    staged: int = 0
    duplicates: int = 0
    # How many newly staged postings were successfully read. Lower than `staged`
    # is normal, not a fault: a good share of ordinary careers sites cannot be
    # read without a browser, and those rows still reach you with a working link.
    enriched: int = 0
    # Discoveries reading has ruled out on graduation timing, cumulative. The
    # number that says whether the eligibility check is doing real work or
    # quietly eating the inbox.
    ruled_out: int = 0
    # Rows re-judged against rules added after they were staged. Costs no
    # network — the posting text was already stored — so it runs every pull.
    rescored: int = 0
    # What each directly-polled company contributed, by name. A company sitting
    # at zero week after week is either paused-worthy or misconfigured, and
    # there is no other way to notice.
    by_company: dict[str, int] = {}
    dropped: dict[str, int] = {}


class DiscoveryPullRequest(BaseModel):
    """What n8n sends to run the nightly pull.

    Identified by email for the same reason the Gmail webhook is: the Pi knows
    which account it is acting for, and nothing else. A user id would mean
    keeping a database key in an automation config, where an email is something
    you can read and check.
    """

    email: str


class DiscoveryRunRead(BaseModel):
    """One pull attempt, as the Discovered page sees it.

    The page shows the most recent of these for one reason: with the pull
    running in the background, an inbox that did not change could mean the feed
    was quiet, the run is still going, or the run died. Those need to look
    different on screen.
    """

    id: str
    state: RunState
    started_at: datetime
    finished_at: datetime | None = None
    fetched: int = 0
    staged: int = 0
    duplicates: int = 0
    enriched: int = 0
    ruled_out: int = 0
    rescored: int = 0
    sources: dict | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class AcceptDiscovered(BaseModel):
    """Optionally supply the posting when accepting a discovery.

    For the rows the enrichment pass could not read — roughly four in ten
    ordinary careers sites need a browser — where the alternative is filing a
    row with a title and a link and nothing to tailor against. Rather than
    discovering that weeks later when you go to write a resume for it, accepting
    is the moment to ask.

    Both optional, and an empty body is the normal case: a posting that was read
    overnight already has everything.
    """

    jd_text: str | None = None
    jd_parsed: dict | None = None
