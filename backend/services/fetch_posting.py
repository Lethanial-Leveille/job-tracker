"""Turn a posting LINK into posting TEXT, so adding a job is a paste of one URL.

This is the front half of the parse flow. services/parsing.py already takes
posting text and returns a ParsedJob; everything here exists only to produce
that text from a link. Nothing in this module knows what a ParsedJob is, and
nothing knows what FastAPI is — same rule as the other services. A route, an
n8n webhook, or a test can all call fetch_posting the same way.

The thing that makes this tractable is that job postings are not really
webpages. Nearly all of them are one of four hiring systems (an ATS, applicant
tracking system) wearing a company's logo, and every one of those four serves
the posting as JSON to anyone who asks the right URL. So this module is a
DISPATCHER: look at the hostname, pick the adapter that knows that system's
JSON shape, and fall back to fetching the page and stripping the tags when the
host is unrecognized.

Why bother with adapters instead of always stripping HTML: Workday. Its page
renders entirely in the browser, so the HTML a script receives contains ONE
character of visible text. A generic scraper does not fail loudly there, it
succeeds and returns nothing, and the parser then hallucinates its way through
an empty posting. The adapter for that host returned the full eleven thousand
character description from the same URL. Workday is also the single most common
ATS among the companies worth applying to, so "just strip the HTML" would have
silently broken the majority case.

Failure here is EXPECTED, not exceptional: LinkedIn and Handshake will never
work, and any site can change shape overnight. So every failure path raises
PostingFetchError with a sentence a human can act on, and the caller's job is
to show that sentence next to the paste box. Fetching is a convenience layered
on top of pasting; pasting stays the thing that always works.
"""

import html
import json
import re
from urllib.parse import parse_qs, urlparse

import httpx

from schemas.parsing import FetchedPosting

# Browsers get served real pages; unlabeled scripts get served challenge pages.
# This is not evasion, it is asking for the same document a person would see.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Generous read timeout, short connect timeout. A host that will not open a
# socket in five seconds is down; a host that is slow to render a big posting
# is normal. You are watching a spinner, so failing fast on the dead case
# matters more than squeezing the slow one.
_TIMEOUT = httpx.Timeout(20.0, connect=5.0)

# Below this many characters, a "successful" fetch is really a failure: a cookie
# wall, a challenge page, or a JavaScript shell. Real postings run to several
# thousand characters. This threshold is the guard against the quiet failure
# described in the module docstring — better to send you to the paste box than
# to hand the parser a nav bar and let it invent a job from it.
_MIN_TEXT_CHARS = 400

# The opposite guard, and the one that costs real money. A single page test
# returned nearly half a million characters: a React application that ships its
# entire routing table and every string in the product as visible text. Handing
# that to the parser burns tokens on a haystack and buries the actual posting in
# it, so anything past this point is cut. Real postings run to roughly ten
# thousand characters, so this leaves a wide margin before it ever bites.
_MAX_TEXT_CHARS = 30_000

# Hosts that will not work, ever, so we say so immediately instead of spending
# twenty seconds proving it. LinkedIn and Indeed serve bot checks to anything
# without a session; Handshake and Glassdoor are behind logins outright, and
# Handshake specifically needs your UF SSO, which no server-side fetch can have.
_BLOCKED_HOSTS = {
    "linkedin.com": "LinkedIn blocks automated fetches.",
    "indeed.com": "Indeed blocks automated fetches.",
    "glassdoor.com": "Glassdoor requires a login.",
    "joinhandshake.com": "Handshake needs your school login, which the server does not have.",
    "app.joinhandshake.com": "Handshake needs your school login, which the server does not have.",
    "ziprecruiter.com": "ZipRecruiter blocks automated fetches.",
}


# A path segment carrying a job id: a UUID, or anything with a long run of
# digits in it ("8052118", "R171666", "XMLNAME-2027-Intern_R171666"). Short
# numbers are excluded deliberately — a "/2/" in a path is far more likely to be
# a page number than an id, and a false positive here rejects a good posting.
_JOB_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\d{5,}",
    re.I,
)

# What a careers site says when the posting is gone. A dead link rarely 404s:
# it redirects to a search page or renders a polite notice, either of which
# scrapes into perfectly good text that a parser will happily turn into a job
# that does not exist.
_GONE_PHRASES = (
    "no longer available",
    "no longer accepting",
    "no longer active",
    "has been filled",
    "position has closed",
    "job not found",
    "posting not found",
    "page not found",
    "this job is closed",
    "we couldn't find",
    "we could not find",
)

# Noise characters per thousand, above which a scrape is a configuration dump
# rather than a job description.
#
# Some careers sites are single-page applications that ship their entire theme
# and routing config as text. One returned nearly half a million characters of
# CSS variables and JSON, and — this is the part that matters — its LIVE posting
# and its DEAD one produced near-identical text, because the description never
# reaches a scraper at all. Truncating that just hands the parser thirty
# thousand characters of colour codes to invent a job from.
#
# The threshold is set from measurement, not taste. Across real postings fetched
# from live job boards the worst offender scored 0.85 and the median 0, while the
# configuration dump scored 117. The margin is roughly thirtyfold in each
# direction, which is what makes this safe to act on.
#
# Semicolons and hash marks were in the counted set at first and were removed:
# both occur in ordinary prose, and dropping them widened the separation from
# thirtyfold to a hundredfold. Only characters that structure serialized data
# and almost never appear in a job description are counted.
_MAX_NOISE_PER_1K = 25.0

# What a careers SITE calls its search page, checked against the page title
# only. This is the last guard, and it exists for one specific class of dead
# link: a site that neither 404s nor redirects, and simply renders its job
# search in place of the posting.
#
# The title is the only honest place to look. Google's dead posting page and its
# live one contain the exact same body text — nav, footer, "back to jobs search",
# even a "3,426 jobs matched" count — because the live posting is rendered inside
# the same search shell. Matching any of that against the body would throw away
# every real Google posting. The titles differ completely: a real one names the
# role, the dead one says "Jobs search". Measured against real scraped postings,
# this list matched none of them.
#
# "404" is deliberately absent: it is a substring of ordinary job ids like 40412.
_LISTING_TITLES = (
    "jobs search",
    "job search",
    "search results",
    "all jobs",
    "job listings",
    "browse jobs",
    "page not found",
    "not found",
    "careers search",
    "search jobs",
    "current openings",
)

# A "gone" phrase only counts on a SHORT page. Error and search pages are brief;
# a real ten thousand character posting that happens to contain "no longer
# accepting" in some clause must not be thrown away over it.
_GONE_MAX_CHARS = 2_500


class _UnknownShape(Exception):
    """This adapter knows the host but cannot read this URL's shape.

    Kept strictly separate from an adapter returning None, and the difference
    decides whether a link fails or falls back to scraping. None means the board
    was ASKED and had no listing, which is grounds for refusing outright. This
    means we never managed to ask, because the link is in a form the adapter
    does not parse — a page that is very likely still a real posting, so it goes
    to the generic scraper instead.

    Conflating the two cost a real posting: a Greenhouse embed link, which is
    about one in ten of them, was reported as a dead listing when it was live.
    """


class PostingFetchError(Exception):
    """The link could not be turned into posting text.

    Carries a sentence meant to be shown to a person, not logged and forgotten:
    the caller puts it above the paste box so you know whether to retry, fix the
    link, or just paste. The service raises rather than returning None (which is
    what parse_job_description does) because there are many distinct reasons a
    fetch fails and "which one" is the whole value of the message.
    """


# --- HTML to text ------------------------------------------------------------


_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)\b.*?</\1>", re.S | re.I)
_BREAKS = re.compile(r"<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", re.I)
_TAGS = re.compile(r"<[^>]+>")
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACE_RUN = re.compile(r"[ \t]{2,}")


def _html_to_text(markup: str) -> str:
    """Strip HTML down to readable text, keeping the line breaks that matter.

    Order is deliberate and each step is load-bearing:

    1. Script and style bodies go FIRST. They are text content as far as a tag
       stripper is concerned, so removing them later means a page's JavaScript
       ends up in the posting the parser reads.
    2. Block-closing tags become newlines BEFORE tags are stripped. Requirements
       are almost always a <li> list, and without this every bullet is welded
       into one paragraph, which is exactly the input that makes an extractor
       merge separate requirements into one.
    3. Entities are unescaped LAST. Doing it earlier would turn a literal
       "&lt;script&gt;" in the posting into a real tag for step 1 to act on.
    """
    text = _SCRIPT_STYLE.sub(" ", markup)
    text = _BREAKS.sub("\n", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    text = _SPACE_RUN.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_RUN.sub("\n\n", text).strip()


def _header(url: str, **fields: str | None) -> str:
    """Build the labeled preamble that goes above every fetched description.

    The description body usually does NOT name the employer — a Workday page
    already knows whose site it is, so the posting never says "Adobe". But
    ParsedJob requires an organization, and a parser handed a description with
    no company name will reach for whatever proper noun it can find.

    So each adapter states what it actually knows as labeled lines, and the
    source URL always appears, because the hostname carries the employer when
    nothing else does. This does not violate the parser's no-inference rule:
    these are facts the ATS returned or the link itself contains, handed over
    as input rather than guessed at by the model.
    """
    lines = [f"{label}: {value}" for label, value in fields.items() if value]
    lines.append(f"Source URL: {url}")
    return "\n".join(lines)


def _embedded_json(markup: str, marker: str) -> dict | None:
    """Pull the JSON object a page assigns to a JavaScript global.

    Single-page job boards ship the posting to the browser as a JSON blob in a
    <script> tag and then render it client side, which is why stripping their
    HTML yields nothing. Reading the blob gets us the same structured data an
    ATS API would return, without the API.

    Brace-matched rather than regex-matched, and the matcher tracks string state
    so that a brace inside the posting text ("salary { negotiable }") does not
    end the object early. A regex cannot do this correctly at any length,
    because JSON nesting is not a regular language.
    """
    index = markup.find(marker)
    if index == -1:
        return None
    try:
        start = markup.index("{", index)
    except ValueError:
        return None

    depth, in_string, escaped = 0, False, False
    for position in range(start, len(markup)):
        char = markup[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(markup[start : position + 1])
                except ValueError:
                    return None
    return None


def _get(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response | None:
    """GET a URL, returning None instead of raising on any non-200 or transport error.

    Adapters use this so that a host-specific path which does not pan out (an ATS
    changed its API, a posting was pulled) falls through to the generic scraper
    rather than killing the whole request. Only fetch_posting itself decides that
    the attempt is over.
    """
    try:
        response = client.get(url, **kwargs)  # type: ignore[arg-type]
    except httpx.HTTPError:
        return None
    return response if response.status_code == 200 else None


# --- Adapters ----------------------------------------------------------------
# Each takes an open client plus the parsed URL and returns posting text, or
# None meaning "I recognized this host but could not get the posting" — which
# sends the caller on to the generic scraper. None is not fatal; only
# fetch_posting turns exhausted options into an error.


def _fetch_workday(client: httpx.Client, url: str, parts: list[str], host: str) -> str | None:
    """Workday: rebuild the page URL as its own JSON endpoint.

    Every Workday page has a hidden twin. This:

        https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/San-Jose/XMLNAME-2027-Intern_R171666

    is served as JSON at:

        https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/job/San-Jose/XMLNAME-2027-Intern_R171666

    The rule: drop the locale segment if present, take the next segment as the
    site id, keep the rest of the path, and insert /wday/cxs/<tenant>/ in front,
    where the tenant is the first label of the hostname ("adobe" from
    "adobe.wd5.myworkdayjobs.com"). The locale is optional in these URLs, hence
    the check rather than an unconditional drop.
    """
    segments = list(parts)
    if segments and re.fullmatch(r"[a-z]{2}-[A-Za-z]{2}", segments[0]):
        segments = segments[1:]
    if len(segments) < 2:
        raise _UnknownShape(url)

    tenant = host.split(".")[0]
    site, rest = segments[0], segments[1:]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/" + "/".join(rest)

    response = _get(client, api, headers={"Accept": "application/json"})
    if response is None:
        return None
    try:
        info = response.json().get("jobPostingInfo") or {}
    except ValueError:
        return None

    body = info.get("jobDescription")
    if not body:
        return None

    # `location` here is a plain string, unlike Greenhouse's nested object.
    header = _header(
        url,
        Title=info.get("title"),
        Location=info.get("location"),
        Posted=info.get("postedOn"),
    )
    return f"{header}\n\n{_html_to_text(body)}"


def _fetch_greenhouse(client: httpx.Client, url: str, parts: list[str], host: str) -> str | None:
    """Greenhouse: the public boards API, which needs the board token and job id.

    Two URL shapes carry those, and both are common:

    - the path form, boards.greenhouse.io/<board>/jobs/<id>. The "jobs" segment
      is located rather than indexed by position, because these URLs sometimes
      carry a locale prefix.
    - the embed form, boards.greenhouse.io/embed/job_app?for=<board>&token=<id>,
      which is roughly one in ten Greenhouse links. Note the `for` parameter is
      often only added by a redirect, so it is the redirected candidate that
      supplies it, not the link as pasted.

    Anything else raises _UnknownShape so the page gets scraped instead of being
    reported as a dead listing. Company careers domains that merely EMBED a
    Greenhouse board (the ?gh_jid= links) never reach here at all, since their
    hostname is the employer's, and the generic scraper handles them well.
    """
    board = job_id = None
    if "jobs" in parts:
        index = parts.index("jobs")
        if index > 0 and index + 1 < len(parts):
            board, job_id = parts[index - 1], parts[index + 1]
    if board is None:
        query = parse_qs(urlparse(url).query)
        board = (query.get("for") or [None])[0]
        job_id = (query.get("token") or [None])[0]
    if not board or not job_id:
        raise _UnknownShape(url)

    response = _get(
        client,
        f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}",
        params={"content": "true"},
    )
    if response is None:
        return None
    try:
        job = response.json()
    except ValueError:
        return None

    body = job.get("content")
    if not body:
        return None

    # Greenhouse double-escapes: `content` is HTML that has itself been entity
    # encoded, so it arrives as "&lt;p&gt;". Unescaping once here turns it back
    # into real markup for _html_to_text, whose own unescape then handles the
    # entities that were in the posting to begin with. Skip this and the parser
    # reads a wall of &lt; and &gt;.
    location = (job.get("location") or {}).get("name")
    header = _header(
        url,
        Title=job.get("title"),
        Company=job.get("company_name"),
        Location=location,
        Deadline=job.get("application_deadline"),
    )
    return f"{header}\n\n{_html_to_text(html.unescape(body))}"


def _fetch_lever(client: httpx.Client, url: str, parts: list[str], host: str) -> str | None:
    """Lever: one posting endpoint, but the description arrives in three pieces.

    The trap: `descriptionPlain` alone looks like the posting and is not. Lever
    splits a posting into an intro (`descriptionPlain`), the bulleted sections
    (`lists`, each a name plus HTML content — this is where requirements and
    qualifications actually live), and a closing block (`additionalPlain`). A
    real posting I checked had six hundred characters of intro and everything
    that matters in `lists`. Taking only the first field yields a fetch that
    succeeds, clears the length floor, and drops every requirement.
    """
    if len(parts) < 2:
        raise _UnknownShape(url)
    company, job_id = parts[0], parts[1]

    response = _get(
        client,
        f"https://api.lever.co/v0/postings/{company}/{job_id}",
        params={"mode": "json"},
    )
    if response is None:
        return None
    try:
        job = response.json()
    except ValueError:
        return None

    sections = [job.get("descriptionPlain") or ""]
    for block in job.get("lists") or []:
        name = block.get("text") or ""
        sections.append(f"{name}\n{_html_to_text(block.get('content') or '')}")
    sections.append(job.get("additionalPlain") or "")

    body = "\n\n".join(part.strip() for part in sections if part and part.strip())
    if not body:
        return None

    categories = job.get("categories") or {}
    header = _header(
        url,
        Title=job.get("text"),
        Location=categories.get("location"),
        Team=categories.get("team"),
    )
    return f"{header}\n\n{body}"


def _fetch_ashby(client: httpx.Client, url: str, parts: list[str], host: str) -> str | None:
    """Ashby: read the posting out of the page's own JSON blob, board API second.

    The obvious route is Ashby's public posting API, and it is the WRONG first
    choice for two reasons. It serves a whole job board per request with no way
    to ask for one posting, so a large employer means downloading megabytes to
    read a few thousand characters. And organizations can turn it off: a real
    posting I tested returned 404 from the board API while the page itself
    carried the full description.

    So the page comes first. Every Ashby posting page assigns window.__appData,
    which holds `posting` (title, descriptionHtml, location) and `organization`
    (the employer's real name, which the URL slug only approximates). One
    request, no megabytes, and it works for boards with the API disabled.

    The board API stays as the fallback for whenever that blob changes shape.
    URLs are jobs.ashbyhq.com/<org>/<uuid>, sometimes with /application and an
    ?embed=true on the end, so the id is always the second path segment.
    """
    response = _get(client, url)
    if response is not None:
        data = _embedded_json(response.text, "window.__appData") or {}
        posting = data.get("posting") or {}
        body = posting.get("descriptionHtml")
        if body:
            header = _header(
                url,
                Title=posting.get("title"),
                Company=(data.get("organization") or {}).get("name"),
                Location=posting.get("locationName"),
                Team=posting.get("departmentName"),
                Deadline=posting.get("applicationDeadline"),
            )
            return f"{header}\n\n{_html_to_text(body)}"

    if len(parts) < 2:
        raise _UnknownShape(url)
    org, job_id = parts[0], parts[1]

    board = _get(client, f"https://api.ashbyhq.com/posting-api/job-board/{org}")
    if board is None:
        return None
    try:
        jobs = board.json().get("jobs") or []
    except ValueError:
        return None

    job = next((item for item in jobs if item.get("id") == job_id), None)
    if job is None:
        return None

    # descriptionPlain is already flat text; descriptionHtml is the fallback for
    # the occasional posting that only carries markup.
    body = job.get("descriptionPlain") or _html_to_text(job.get("descriptionHtml") or "")
    if not body:
        return None

    header = _header(
        url,
        Title=job.get("title"),
        Location=job.get("location"),
        Team=job.get("team") or job.get("department"),
        Posted=job.get("publishedAt"),
    )
    return f"{header}\n\n{body}"


def _fetch_generic(client: httpx.Client, url: str) -> str | None:
    """Any other host: fetch the page and strip it to text.

    Works on ordinary server-rendered careers pages, which is most of what is
    left once the four big systems are handled. Returns None on a non-HTML
    response so that a link to a PDF or an image does not get run through the
    tag stripper and come back as binary noise.
    """
    response = _get(client, url)
    if response is None:
        return None
    if "html" not in response.headers.get("content-type", "").lower():
        return None

    # Returned even when the stripped text is empty, rather than None. An empty
    # HTML page IS a result: it means the page renders in the browser, and the
    # length floor in fetch_posting turns that into "needs a browser to render",
    # which is the accurate diagnosis. Returning None here instead would report
    # the same page as unreadable, which is vaguer and slightly wrong.
    return f"{_header(url)}\n\n{_html_to_text(response.text)}"


# --- Entry point -------------------------------------------------------------

# Hostname suffix, adapter name, adapter. Every adapter takes the same four
# arguments so this stays a table; the ones that do not need `host` ignore it.
# Order does not matter, the suffixes are mutually exclusive.
SOURCE_LABELS = {
    "workday": "Workday",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}

_ADAPTERS: tuple[tuple[str, str, object], ...] = (
    ("myworkdayjobs.com", "workday", _fetch_workday),
    ("greenhouse.io", "greenhouse", _fetch_greenhouse),
    ("lever.co", "lever", _fetch_lever),
    ("ashbyhq.com", "ashby", _fetch_ashby),
)


# A hostname has no spaces and, outside of a local dev box, has a dot in it.
# urlparse validates none of this: it happily reports "not a url at all" as the
# netloc of "https://not a url at all", so without this check a typo becomes a
# real request and a twenty second wait instead of an instant answer.
_HOSTLIKE = re.compile(r"[A-Za-z0-9\-._~%]+(:\d+)?$")


def _is_hostlike(netloc: str) -> bool:
    return bool(netloc) and "." in netloc and _HOSTLIKE.fullmatch(netloc) is not None


def _host_of(parsed: object) -> str:
    return parsed.netloc.lower().removeprefix("www.")  # type: ignore[attr-defined]


def _check_blocked(host: str) -> None:
    """Raise if this host is one we know will never serve a posting to a script."""
    for blocked, reason in _BLOCKED_HOSTS.items():
        if host == blocked or host.endswith(f".{blocked}"):
            raise PostingFetchError(f"{reason} Paste the posting text instead.")


def _looks_gone(text: str) -> bool:
    """True when a page reads like a dead posting rather than a live one."""
    if len(text) > _GONE_MAX_CHARS:
        return False
    lowered = text.lower()
    return any(phrase in lowered for phrase in _GONE_PHRASES)


def _noise_density(text: str) -> float:
    """Braces, brackets and quotes per thousand characters.

    A crude but strongly separating measure of "is this prose". Job descriptions
    are words; serialized configuration is punctuation.
    """
    return sum(text.count(c) for c in '{}[]"') * 1000 / max(len(text), 1)


def _looks_like_a_listing(text: str) -> bool:
    """True when a scraped page's title says it is a job search, not a job.

    Only ever applied to a generic scrape. A job board adapter's text starts
    with the description rather than a page title, so there is nothing here for
    it to read and nothing for it to get wrong.
    """
    body = text.split("\n\n", 1)[1] if "\n\n" in text else ""
    title = next((line for line in body.splitlines() if line.strip()), "").lower()
    return any(marker in title for marker in _LISTING_TITLES)


def _redirected_off_the_posting(requested: str, landed: str) -> bool:
    """True when a site bounced us away from the posting to somewhere generic.

    A dead job link almost never answers 404. It redirects to the careers search
    page, which returns a real HTTP 200 full of real text that scrapes cleanly
    and parses into a plausible job that does not exist. That is the worst
    possible failure for this feature, so it gets its own check.

    The signal is precise: if the link you gave contains a job id and the page
    you landed on no longer mentions that id, the site swapped the posting for
    something else. When the original URL carries no id-shaped segment there is
    nothing to check and this returns False rather than guessing.
    """
    ids = set(_JOB_ID.findall(requested))
    if not ids:
        return False
    return not any(job_id.lower() in landed.lower() for job_id in ids)


def fetch_posting(url: str) -> FetchedPosting:
    """Fetch a posting link and return its text, or raise PostingFetchError.

    Callers pass the resulting `.text` straight to parse_job_description and
    store it on the application as jd_text.

    The governing rule is that a REFUSAL BEATS A PLAUSIBLE WRONG ANSWER. A job
    that does not exist, entered from a page that was never a posting, is worse
    than no result at all: you would apply to it, or worse, believe you had. So
    four things are treated as failures rather than as thin successes.

    A recognized job board whose own listing comes up empty fails outright, with
    no fall back to scraping the page. This costs something real — if one of
    those systems changes its API, every link to it fails until the adapter is
    fixed — and it is the right trade, because when a job board says it does not
    have a posting, the page still sitting at that URL is a search page or a
    notice, not the job.

    A site that redirects away from the posting fails, even though the page it
    lands on returns a perfectly good 200. A page that reads like a dead listing
    fails. And a page too short to be a posting fails, which is what catches the
    ones that only render in a browser.

    Dispatch tries the link AS GIVEN before its redirect target. That looks
    backwards and is the whole fix for Greenhouse: those links now bounce to the
    employer's own careers domain, so resolving redirects first would throw away
    the only signal saying which system this is.
    """
    parsed = urlparse(url.strip() if "://" in url else f"https://{url.strip()}")
    if parsed.scheme not in ("http", "https") or not _is_hostlike(parsed.netloc):
        raise PostingFetchError("That does not look like a link. Paste the posting text instead.")

    normalized = parsed.geturl()
    _check_blocked(_host_of(parsed))

    with httpx.Client(
        headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
    ) as client:
        target, final = normalized, parsed
        try:
            landed = client.head(normalized, follow_redirects=True)
            target = str(landed.url)
            final = urlparse(target)
            if _host_of(final) != _host_of(parsed):
                _check_blocked(_host_of(final))
        except httpx.HTTPError:
            pass

        # Candidates in dispatch order: the link as given, then its destination
        # if that is a different host.
        candidates = [(normalized, parsed)]
        if _host_of(final) != _host_of(parsed):
            candidates.append((target, final))

        source, text, matched = "generic", None, False
        for candidate_url, candidate in candidates:
            host = _host_of(candidate)
            parts = [segment for segment in candidate.path.split("/") if segment]
            for suffix, name, adapter in _ADAPTERS:
                if not host.endswith(suffix):
                    continue
                try:
                    text = adapter(client, candidate_url, parts, host)  # type: ignore[operator]
                except _UnknownShape:
                    # Not a match at all: we never got to ask the board, so this
                    # link keeps its chance at the generic scraper below.
                    break
                matched = True
                source = name
                break
            if text is not None:
                break

        if matched and text is None:
            # No scrape fallback here, on purpose. See the docstring: the page
            # still at this URL is not the posting the job board just disclaimed.
            raise PostingFetchError(
                f"That {SOURCE_LABELS.get(source, source)} listing is not there any more, "
                "or the link is wrong. Paste the posting text instead."
            )

        if text is None:
            if _redirected_off_the_posting(normalized, target):
                raise PostingFetchError(
                    "That link redirected away from the posting, which usually means "
                    "the job is gone. Paste the posting text instead."
                )
            text = _fetch_generic(client, target)

    if text is None:
        raise PostingFetchError(
            "Could not read that page. Paste the posting text instead."
        )
    if len(text) < _MIN_TEXT_CHARS:
        raise PostingFetchError(
            "That page loaded but had almost no text on it, which usually means "
            "the posting needs a browser to render. Paste the posting text instead."
        )
    if _looks_gone(text):
        raise PostingFetchError(
            "That page says the posting is closed or missing. Paste the posting "
            "text instead."
        )
    if source == "generic" and _looks_like_a_listing(text):
        raise PostingFetchError(
            "That link opened a job search page rather than a posting, which "
            "usually means the job is gone. Paste the posting text instead."
        )
    # Generic scrapes only. A job board adapter's text came from that board's own
    # listing for this job, so it is authoritative by definition and does not get
    # second-guessed on style.
    if source == "generic" and _noise_density(text) > _MAX_NOISE_PER_1K:
        raise PostingFetchError(
            "That page returned its own code rather than the posting, which "
            "means it needs a browser to render. Paste the posting text instead."
        )
    if len(text) > _MAX_TEXT_CHARS:
        # Truncated rather than rejected: the posting is nearly always at the top
        # of an over-large page, and a truncated parse beats no parse. The marker
        # is there so that a thin result has a visible explanation in jd_text.
        text = text[:_MAX_TEXT_CHARS] + "\n\n[truncated by the fetcher]"
    return FetchedPosting(text=text, source=source, url=target)
