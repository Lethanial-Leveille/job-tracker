"""Shapes for the discovery feed: what a listing looks like coming in, and what
a staged job looks like going back out to the UI.

Two very different kinds of model live here on purpose. FeedListing describes
data we do not control and cannot correct — a public file republished daily by
someone else. Everything below it describes our own rows.
"""

from datetime import UTC, date, datetime

from pydantic import BaseModel

from models.discovered_job import DiscoveryState


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
    dropped: dict[str, int] = {}


class DiscoveryPullRequest(BaseModel):
    """What n8n sends to run the nightly pull.

    Identified by email for the same reason the Gmail webhook is: the Pi knows
    which account it is acting for, and nothing else. A user id would mean
    keeping a database key in an automation config, where an email is something
    you can read and check.
    """

    email: str
