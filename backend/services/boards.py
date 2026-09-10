"""Reading a whole job board, one employer at a time.

The second discovery source. services/feed.py reads an aggregator that covers
thousands of companies a day late; this reads five applicant tracking systems
directly, for a handful of companies you chose, the moment they publish.

Every function here returns the same shape — a list of BoardPosting — so the
staging service does not care which system a job came from. What differs is
only how each vendor spells "give me your open roles".

Three of these five were already half-written. The single-posting adapters in
services/fetch_posting.py call board-wide endpoints for Greenhouse, Lever and
Ashby, because that is simply how those APIs work: you ask for the board and
pick one out. Workday and Oracle are different — their single-posting lookups
take a job id, and listing a board is a separate endpoint with its own shape.
Those two are new here.

Politeness is not optional and is not decoration. These are other people's
servers, being polled nightly by a personal tool with no agreement in place. So
every request is sequential, spaced, and honestly labelled. See _polite.
"""

import re
import time
from datetime import date, datetime

import httpx
from pydantic import BaseModel

from services.fetch_posting import _HEADERS, _html_to_text

# Generous, because a board listing is one request that either works or does
# not, and a slow employer is not a broken one.
_TIMEOUT = httpx.Timeout(45.0, connect=10.0)

# Seconds between consecutive requests to the same vendor. Small, because a
# nightly run makes a few dozen requests in total, and the point is to avoid
# looking like a burst rather than to be slow.
_DELAY = 1.0

# How many postings to take from one board. A cap rather than full pagination:
# these are sorted newest first, and a company posting more than this many roles
# overnight is not a situation more pages would improve.
_PAGE = 100

# Oracle's keyword search is loose, so ask for a wide slice and let the title
# filter do the work.
_ORACLE_SCAN = 200

_last_request_at: dict[str, float] = {}

# A job board carries every open role at the company, and internships are a
# small minority — Stripe's board had 620 jobs and 7 internships. Without this
# gate the classifier is handed "Engineering Manager, Agent" and, because every
# family it knows ends in "Intern", it picks the nearest one and a senior
# full-time role lands in the inbox looking like a match.
#
# The aggregator feed needs none of this: it is an internships-only list, so it
# provided the filter for free. A company board does not, and that difference is
# the single biggest thing separating the two sources.
#
# Word-bounded so "internal" and "international" do not match, which they would
# on a bare prefix and which is most of a large company's postings.
_INTERNSHIP = re.compile(
    r"\b(intern|interns|internship|internships|co-?op|co-?ops|apprentice|apprenticeship)\b",
    re.I,
)


def is_internship(title: str) -> bool:
    """True when a job title says it is an internship.

    The vendors' own search parameters help but cannot be trusted: Workday's
    `searchText=intern` still returns "Product Manager - International Strategy"
    and Oracle's keyword search returns supply chain roles. They are worth
    sending to narrow what comes back; they are not worth believing.
    """
    return bool(_INTERNSHIP.search(title))


def _polite(client: httpx.Client, method: str, url: str, host: str, **kwargs: object):
    """Make one request, no faster than one per host per _DELAY seconds.

    Sequential and spaced on purpose. These are other people's servers and this
    is a personal tool polling them nightly with no arrangement in place, so the
    right shape is a trickle that looks like a person rather than a burst that
    looks like a scraper. The user agent comes from services/fetch_posting.py,
    which is a real browser string — not to disguise anything, but because an
    unlabelled script gets served a challenge page instead of a board.

    Returns the response or None. Never raises: one unreachable company must not
    end a run that has four others to do.
    """
    previous = _last_request_at.get(host)
    if previous is not None:
        wait = _DELAY - (time.monotonic() - previous)
        if wait > 0:
            time.sleep(wait)
    _last_request_at[host] = time.monotonic()

    try:
        response = client.request(method, url, **kwargs)  # type: ignore[arg-type]
    except httpx.HTTPError:
        return None
    return response if response.status_code == 200 else None


class BoardPosting(BaseModel):
    """One open role, as read from an employer's own board.

    Deliberately the same few fields the aggregator feed provides, so staging
    treats both sources identically. Anything richer belongs to the enrichment
    pass, which reads the posting properly.
    """

    external_id: str
    title: str
    url: str
    location: str | None = None
    posted_at: date | None = None


def _as_date(value: object) -> date | None:
    """Parse whatever a vendor calls a date, or give up quietly.

    Vendors disagree about format and some omit it entirely. A missing posted
    date is not worth failing a company over — it costs the inbox its sort order
    for one row.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


# --- The five ----------------------------------------------------------------


def greenhouse(client: httpx.Client, board: str) -> list[BoardPosting]:
    """Greenhouse: the same public boards API the link adapter uses.

    `content=false` on purpose. The full description of every role at a company
    is megabytes we would immediately throw away — enrichment fetches the one
    posting you care about later, and only for jobs that survive filtering.
    """
    response = _polite(
        client,
        "GET",
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
        "greenhouse.io",
    )
    if response is None:
        return []
    postings = []
    # The cap applies AFTER filtering, not before. Greenhouse has no server-side
    # search, so the whole board comes back and the internships are scattered
    # through it — capping first is how you read 100 senior roles and conclude
    # the company has no internships.
    for job in response.json().get("jobs") or []:
        if not is_internship(job.get("title") or ""):
            continue
        if len(postings) >= _PAGE:
            break
        postings.append(
            BoardPosting(
                external_id=str(job.get("id")),
                title=job.get("title") or "",
                url=job.get("absolute_url") or "",
                location=(job.get("location") or {}).get("name"),
                posted_at=_as_date(job.get("first_published") or job.get("updated_at")),
            )
        )
    return postings


def lever(client: httpx.Client, board: str) -> list[BoardPosting]:
    """Lever: the public postings list.

    Unlike the single-posting adapter, nothing here has to reassemble the
    description out of three fields — the listing carries only the summary
    fields, which is all staging needs.
    """
    response = _polite(
        client,
        "GET",
        f"https://api.lever.co/v0/postings/{board}",
        "lever.co",
        params={"mode": "json"},
    )
    if response is None:
        return []
    postings = []
    for job in response.json() or []:
        if not is_internship(job.get("text") or ""):
            continue
        if len(postings) >= _PAGE:
            break
        categories = job.get("categories") or {}
        postings.append(
            BoardPosting(
                external_id=str(job.get("id")),
                title=job.get("text") or "",
                url=job.get("hostedUrl") or job.get("applyUrl") or "",
                location=categories.get("location"),
                # Milliseconds since the epoch, unlike everyone else's ISO string.
                posted_at=(
                    datetime.fromtimestamp(job["createdAt"] / 1000).date()
                    if isinstance(job.get("createdAt"), (int, float))
                    else None
                ),
            )
        )
    return postings


def ashby(client: httpx.Client, board: str) -> list[BoardPosting]:
    """Ashby: the public job board endpoint.

    This is the one case where the wasteful call in the link adapter is the
    right call here: Ashby serves a whole board per request and nothing else,
    which is exactly what we want when reading a whole board.
    """
    response = _polite(
        client,
        "GET",
        f"https://api.ashbyhq.com/posting-api/job-board/{board}",
        "ashbyhq.com",
    )
    if response is None:
        return []
    postings = []
    for job in response.json().get("jobs") or []:
        if not is_internship(job.get("title") or ""):
            continue
        if len(postings) >= _PAGE:
            break
        postings.append(
            BoardPosting(
                external_id=str(job.get("id")),
                title=job.get("title") or "",
                url=job.get("jobUrl") or job.get("applyUrl") or "",
                location=job.get("location"),
                posted_at=_as_date(job.get("publishedAt")),
            )
        )
    return postings


# Workday rejects any page larger than this with a 400 and an empty message,
# which is a memorable way to spend twenty minutes. Everyone else accepts 100.
_WORKDAY_PAGE = 20

# How deep to page before giving up. Twenty requests at one a second is the most
# a single employer should cost a nightly run, and a company whose internships
# are past the four hundredth search result for "intern" is not one this is
# going to find.
_WORKDAY_SCAN = 400


def workday(client: httpx.Client, host: str, tenant: str, site: str) -> list[BoardPosting]:
    """Workday: a paginated POST search, which is why this could not be reused.

    Three things here are unlike every other reader and all three were found by
    running it:

    - Listing a board is a POST with a JSON body, not a GET. It is Workday's
      faceted search with every facet left empty, which looks like a mistake and
      is not.
    - The page size caps at 20. Asking for 50 returns a 400 with no message at
      all, so this pages rather than asking once.
    - The response gives relative paths ("/job/San-Jose/..."), so links are
      rebuilt against the tenant's public site. Get that wrong and every posting
      links somewhere that 404s.

    There is also no usable date: Workday reports "Posted 7 Days Ago" as prose.
    Parsing English into a date is how a posting ends up sorted a week wrong, so
    it is left to the enrichment pass, which reads the real posting.
    """
    postings: list[BoardPosting] = []
    # Page through a bounded slice rather than the whole board. `searchText`
    # narrows it but is fuzzy — it happily returns "Product Manager -
    # International Strategy" for "intern" — so the real filter is the title,
    # and this bound is what stops a company with three thousand roles from
    # turning one nightly run into a thousand requests.
    for offset in range(0, _WORKDAY_SCAN, _WORKDAY_PAGE):
        response = _polite(
            client,
            "POST",
            f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
            host,
            json={
                "appliedFacets": {},
                "limit": _WORKDAY_PAGE,
                "offset": offset,
                "searchText": "intern",
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if response is None:
            break
        page = response.json().get("jobPostings") or []
        for job in page:
            path = job.get("externalPath") or ""
            title = job.get("title") or ""
            if not path or not is_internship(title):
                continue
            # bulletFields carries the requisition id, and is occasionally empty.
            bullets = job.get("bulletFields") or []
            postings.append(
                BoardPosting(
                    external_id=bullets[0] if bullets else path,
                    title=title,
                    url=f"https://{host}/{site}{path}",
                    location=job.get("locationsText"),
                    posted_at=None,
                )
            )
        if len(page) < _WORKDAY_PAGE or len(postings) >= _PAGE:
            break
    return postings[:_PAGE]


def oracle(client: httpx.Client, host: str, site: str) -> list[BoardPosting]:
    """Oracle Cloud recruiting: the requisition list, also new here.

    The single-posting adapter fetches one requisition by id; this asks for the
    list. Note the finder syntax, which is Oracle's own query language stuffed
    into a query parameter, and the nesting: the real rows are one level down
    inside items[0].requisitionList rather than in items itself.

    Sorted newest first by the server, because there is no posted date on these
    rows to sort by afterwards.
    """
    response = _polite(
        client,
        "GET",
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
        host,
        params={
            "onlyData": "true",
            # `expand` is not optional despite the name. Without it the response
            # is a 200 carrying only facets and counts — the requisitions
            # themselves are simply absent, so the reader silently returns
            # nothing and looks like a company with no open roles.
            "expand": "requisitionList.secondaryLocations",
            # `keyword` narrows what comes back and is no more trustworthy
            # than Workday's — Dell's returned supply chain roles for "intern" —
            # so the title filter below is what actually decides. The larger
            # limit is because the keyword is loose enough that the real
            # internships can sit well down the list.
            "finder": (
                f"findReqs;siteNumber={site},keyword=intern,"
                f"limit={_ORACLE_SCAN},sortBy=POSTING_DATES_DESC"
            ),
        },
        headers={"Accept": "application/json"},
    )
    if response is None:
        return []
    items = response.json().get("items") or []
    if not items:
        return []
    postings = []
    for job in items[0].get("requisitionList") or []:
        job_id = str(job.get("Id") or "")
        title = _html_to_text(job.get("Title") or "")
        if not job_id or not is_internship(title):
            continue
        if len(postings) >= _PAGE:
            break
        postings.append(
            BoardPosting(
                external_id=job_id,
                title=title,
                url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{job_id}",
                location=job.get("PrimaryLocation"),
                posted_at=_as_date(job.get("PostedDate")),
            )
        )
    return postings


# Dispatch by ATS name. Each entry takes the TargetCompany's three identifier
# columns and knows which of them its own vendor needs.
READERS = {
    "greenhouse": lambda c, host, board, site: greenhouse(c, board or ""),
    "lever": lambda c, host, board, site: lever(c, board or ""),
    "ashby": lambda c, host, board, site: ashby(c, board or ""),
    "workday": lambda c, host, board, site: workday(c, host or "", board or "", site or ""),
    "oracle": lambda c, host, board, site: oracle(c, host or "", site or ""),
}


def read_board(ats: str, host: str | None, board: str | None, site: str | None) -> list[BoardPosting]:
    """Read one company's board. Returns an empty list rather than raising.

    A company that will not answer is a line in the run record, not the end of
    the run — there are four others waiting.
    """
    reader = READERS.get(ats)
    if reader is None:
        return []
    with httpx.Client(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as client:
        return reader(client, host, board, site)
