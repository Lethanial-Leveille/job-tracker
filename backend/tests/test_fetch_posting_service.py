"""Tests for the posting fetcher.

The service's whole job is talking to the open internet, which is exactly what
a test must not do — the same instinct as the in-memory DB fixture and the
mocked Anthropic client. Real job postings also disappear, so a test pinned to a
live URL would start failing for reasons that have nothing to do with this code.

So every test here fakes the HTTP layer by patching `httpx.Client` where the
service uses it, and asserts the service's OWN logic: that it picks the right
adapter for a host, digs the description out of each ATS's particular JSON
shape, and turns each failure into a message a person can act on.

The adapters were verified by hand against live postings from all four hiring
systems before these were written. That is the same split as
test_parsing_service.py: mechanics here, reality checked by hand.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.fetch_posting import (
    PostingFetchError,
    _embedded_json,
    _html_to_text,
    fetch_posting,
)

# Long enough to clear _MIN_TEXT_CHARS, so a test asserting routing is never
# tripped up by the length floor it is not trying to exercise.
_BODY = "<ul><li>Requirement one</li><li>Requirement two</li></ul>" + ("word " * 200)


def _response(*, status: int = 200, json_body: object = None, text: str = "", html: bool = True) -> MagicMock:
    """Stand in for an httpx.Response.

    `.json()` raises ValueError on a non-JSON body, mirroring httpx, because the
    adapters rely on catching exactly that to fall through.
    """
    response = MagicMock()
    response.status_code = status
    response.text = json.dumps(json_body) if json_body is not None else text
    response.headers = {"content-type": "text/html" if html else "application/pdf"}
    if json_body is None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_body
    return response


def _client(routes: dict[str, MagicMock], *, landing: str | None = None) -> MagicMock:
    """A fake httpx.Client whose GETs are looked up by URL substring.

    Matching on a substring rather than the exact URL keeps the tests readable:
    they say "the Workday JSON endpoint" without restating query strings the
    adapter builds. `landing` is the URL the initial HEAD redirects to, which is
    how the redirect-ordering tests steer dispatch.
    """
    client = MagicMock()
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    head = MagicMock()
    head.url = landing or "https://example.com/job"
    client.head.return_value = head

    def get(url: str, **kwargs: object) -> MagicMock:
        for fragment, response in routes.items():
            if fragment in url:
                return response
        return _response(status=404)

    client.get.side_effect = get
    return client


# --- HTML to text ------------------------------------------------------------


def test_html_to_text_drops_script_bodies() -> None:
    # Script contents are text to a naive tag stripper, so a page's JavaScript
    # would otherwise end up in the posting the parser reads.
    text = _html_to_text("<p>Real</p><script>var secret = 1;</script>")
    assert "Real" in text
    assert "secret" not in text


def test_html_to_text_keeps_list_items_on_separate_lines() -> None:
    # Requirements are almost always a <li> list. Welded into one line, an
    # extractor reads several separate requirements as one.
    text = _html_to_text("<ul><li>Python</li><li>SQL</li></ul>")
    assert "Python\nSQL" in text


def test_html_to_text_unescapes_after_stripping() -> None:
    # Unescaping first would turn this literal text into a real tag for the
    # script remover to act on.
    assert "<script>" in _html_to_text("<p>&lt;script&gt;</p>")


# --- Embedded JSON extraction ------------------------------------------------


def test_embedded_json_survives_braces_inside_strings() -> None:
    # The reason this is a brace matcher that tracks string state and not a
    # regex: a brace in the posting text must not end the object early.
    blob = _embedded_json('window.__appData = {"a": "salary { negotiable }", "b": 2};', "window.__appData")
    assert blob == {"a": "salary { negotiable }", "b": 2}


def test_embedded_json_handles_escaped_quotes() -> None:
    blob = _embedded_json(r'x = {"a": "she said \"hi\"", "b": {"c": 1}};', "x =")
    assert blob == {"a": 'she said "hi"', "b": {"c": 1}}


def test_embedded_json_returns_none_when_marker_absent() -> None:
    assert _embedded_json("<html>nothing here</html>", "window.__appData") is None


# --- Adapter routing ---------------------------------------------------------


@patch("services.fetch_posting.httpx.Client")
def test_workday_rebuilds_the_url_as_its_json_endpoint(mock_client: MagicMock) -> None:
    mock_client.return_value = _client(
        {"/wday/cxs/adobe/external_experienced/job/San-Jose/R1": _response(
            json_body={"jobPostingInfo": {"title": "Intern", "location": "San Jose", "jobDescription": _BODY}}
        )},
        landing="https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/San-Jose/R1",
    )

    result = fetch_posting("https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced/job/San-Jose/R1")

    assert result.source == "workday"
    assert "Title: Intern" in result.text
    assert "Requirement one" in result.text


@patch("services.fetch_posting.httpx.Client")
def test_workday_url_without_a_locale_segment(mock_client: MagicMock) -> None:
    # The locale is optional in Workday URLs, so the adapter checks for one
    # rather than dropping the first segment unconditionally.
    mock_client.return_value = _client(
        {"/wday/cxs/adobe/external/job/R1": _response(
            json_body={"jobPostingInfo": {"title": "Intern", "jobDescription": _BODY}}
        )},
        landing="https://adobe.wd5.myworkdayjobs.com/external/job/R1",
    )

    assert fetch_posting("https://adobe.wd5.myworkdayjobs.com/external/job/R1").source == "workday"


@patch("services.fetch_posting.httpx.Client")
def test_greenhouse_adapter_wins_over_the_redirect_target(mock_client: MagicMock) -> None:
    """The ordering fix, as a test.

    A boards.greenhouse.io link now redirects to the employer's own careers
    domain. Dispatching on the redirect target would lose the only signal that
    this is Greenhouse and quietly fall back to scraping, so the link AS GIVEN
    is tried first. `landing` here is the employer domain, exactly as in life.
    """
    mock_client.return_value = _client(
        {"boards-api.greenhouse.io/v1/boards/stripe/jobs/123": _response(
            json_body={"title": "Intern", "company_name": "Stripe",
                       "location": {"name": "Seattle"}, "content": _BODY}
        )},
        landing="https://stripe.com/careers/listing/intern/123",
    )

    result = fetch_posting("https://boards.greenhouse.io/stripe/jobs/123")

    assert result.source == "greenhouse"
    assert "Company: Stripe" in result.text


@patch("services.fetch_posting.httpx.Client")
def test_lever_gathers_all_three_description_fields(mock_client: MagicMock) -> None:
    """The Lever trap: descriptionPlain alone looks like the posting and is not.

    Requirements live in `lists`, and a fetch that took only the intro would
    succeed, clear the length floor, and silently drop every requirement.
    """
    mock_client.return_value = _client(
        {"api.lever.co/v0/postings/acme/abc": _response(
            json_body={
                "text": "Intern",
                "descriptionPlain": "Intro paragraph. " + ("word " * 100),
                "lists": [{"text": "Requirements", "content": "<li>Python</li>"}],
                "additionalPlain": "Closing note.",
                "categories": {"location": "Remote", "team": "Eng"},
            }
        )},
        landing="https://jobs.lever.co/acme/abc",
    )

    text = fetch_posting("https://jobs.lever.co/acme/abc").text

    assert "Intro paragraph" in text
    assert "Requirements" in text and "Python" in text
    assert "Closing note" in text


@patch("services.fetch_posting.httpx.Client")
def test_ashby_reads_the_page_blob_before_the_board_api(mock_client: MagicMock) -> None:
    """Ashby's page JSON is the primary path, not its public API.

    Some organizations switch the board API off entirely — a real posting
    returned 404 from it while its own page carried the full description — and
    the API serves a whole board per request besides. This asserts the board API
    is never called when the page blob is readable.
    """
    blob = json.dumps({
        "organization": {"name": "Whatnot"},
        "posting": {"title": "Intern", "locationName": "SF", "descriptionHtml": _BODY},
    })
    client = _client(
        {"jobs.ashbyhq.com": _response(text=f"<script>window.__appData = {blob};</script>")},
        landing="https://jobs.ashbyhq.com/whatnot/abc/application",
    )
    mock_client.return_value = client

    result = fetch_posting("https://jobs.ashbyhq.com/whatnot/abc/application")

    assert result.source == "ashby"
    assert "Company: Whatnot" in result.text
    assert not any("posting-api" in call.args[0] for call in client.get.call_args_list)


@patch("services.fetch_posting.httpx.Client")
def test_ashby_falls_back_to_the_board_api(mock_client: MagicMock) -> None:
    mock_client.return_value = _client(
        {
            "jobs.ashbyhq.com": _response(text="<html>no blob here</html>"),
            "posting-api/job-board/acme": _response(
                json_body={"jobs": [{"id": "abc", "title": "Intern", "descriptionPlain": _BODY}]}
            ),
        },
        landing="https://jobs.ashbyhq.com/acme/abc",
    )

    assert fetch_posting("https://jobs.ashbyhq.com/acme/abc").source == "ashby"


@patch("services.fetch_posting.httpx.Client")
def test_unknown_host_is_scraped(mock_client: MagicMock) -> None:
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=f"<html><body>{_BODY}</body></html>")},
        landing="https://careers.acme.com/jobs/1",
    )

    result = fetch_posting("https://careers.acme.com/jobs/1")

    assert result.source == "generic"
    assert "Requirement one" in result.text


@patch("services.fetch_posting.httpx.Client")
def test_known_board_with_no_listing_refuses_instead_of_scraping(mock_client: MagicMock) -> None:
    """The rule Lee set: a refusal beats a plausible wrong answer.

    When a job board's own API has no listing at this id, the page still sitting
    at the URL is a search page or a "no longer available" notice. Scraping it
    yields real text that parses into a real-looking job that does not exist,
    which is the worst outcome this feature can produce — you would apply to it,
    or believe you had. So a recognized board that comes up empty is a hard
    failure, and the page is never scraped.

    This costs something: if a board changes its API, every link to it fails
    until the adapter is fixed. That is the accepted trade.
    """
    client = _client(
        {
            "/wday/cxs/": _response(status=404),
            "myworkdayjobs.com": _response(text=f"<html><body>{_BODY}</body></html>"),
        },
        landing="https://acme.wd1.myworkdayjobs.com/en-US/careers/job/R12345",
    )
    mock_client.return_value = client

    with pytest.raises(PostingFetchError, match="Workday listing is not there"):
        fetch_posting("https://acme.wd1.myworkdayjobs.com/en-US/careers/job/R12345")


@patch("services.fetch_posting.httpx.Client")
def test_redirect_away_from_the_job_id_is_refused(mock_client: MagicMock) -> None:
    """A dead posting almost never answers 404.

    It redirects to the careers search page, which returns a real 200 full of
    real text. Nothing else in this service can tell that apart from a posting,
    so the check is on the id: the link named job 8052118 and the page we landed
    on does not mention it, which means the site swapped the posting for
    something else.
    """
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=f"<html><body>{_BODY}</body></html>")},
        landing="https://careers.acme.com/search",
    )

    with pytest.raises(PostingFetchError, match="redirected away from the posting"):
        fetch_posting("https://careers.acme.com/jobs/8052118")


@patch("services.fetch_posting.httpx.Client")
def test_redirect_that_keeps_the_job_id_is_fine(mock_client: MagicMock) -> None:
    # The other half of the check, and the reason it is about the id rather than
    # about redirecting at all: employers routinely redirect a posting to a
    # prettier URL for the same job, and that must keep working.
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=f"<html><body>{_BODY}</body></html>")},
        landing="https://careers.acme.com/listing/backend-intern/8052118",
    )

    assert fetch_posting("https://careers.acme.com/jobs/8052118").source == "generic"


@patch("services.fetch_posting.httpx.Client")
def test_a_link_with_no_id_is_not_judged_on_redirects(mock_client: MagicMock) -> None:
    # No id in the link means there is nothing to check, so the guard must stay
    # out of the way rather than guess. Guessing here would reject good pages.
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=f"<html><body>{_BODY}</body></html>")},
        landing="https://careers.acme.com/somewhere-else",
    )

    assert fetch_posting("https://careers.acme.com/internships").source == "generic"


@patch("services.fetch_posting.httpx.Client")
def test_a_page_saying_the_job_is_gone_is_refused(mock_client: MagicMock) -> None:
    gone = "<p>This position is no longer accepting applications.</p>" + ("word " * 90)
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=gone)},
        landing="https://careers.acme.com/jobs/1",
    )

    with pytest.raises(PostingFetchError, match="closed or missing"):
        fetch_posting("https://careers.acme.com/jobs/1")


@patch("services.fetch_posting.httpx.Client")
def test_a_real_posting_is_not_rejected_for_containing_that_phrase(mock_client: MagicMock) -> None:
    """The false positive this guard has to avoid.

    A long posting can legitimately contain "no longer accepting" in some
    clause. Only a SHORT page counts, because error and search pages are brief
    and real postings are not — without that, the guard would start throwing
    away good jobs, which is the failure mode we are supposedly preventing.
    """
    posting = "<p>Applications close soon and we are no longer accepting referrals.</p>" + ("word " * 900)
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=posting)},
        landing="https://careers.acme.com/jobs/1",
    )

    assert len(fetch_posting("https://careers.acme.com/jobs/1").text) > 2_500


@patch("services.fetch_posting.httpx.Client")
def test_greenhouse_embed_url_shape(mock_client: MagicMock) -> None:
    """The embed form, which is roughly one in ten Greenhouse links.

    The board name arrives as a `for` query parameter rather than a path
    segment, and often only after a redirect adds it. Before this was handled,
    these were reported as dead listings while the job was live.
    """
    mock_client.return_value = _client(
        {"boards-api.greenhouse.io/v1/boards/coinbase/jobs/8168315": _response(
            json_body={"title": "Intern", "company_name": "Coinbase", "content": _BODY}
        )},
        landing="https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=8168315",
    )

    result = fetch_posting("https://boards.greenhouse.io/embed/job_app?token=8168315")

    assert result.source == "greenhouse"
    assert "Company: Coinbase" in result.text


@patch("services.fetch_posting.httpx.Client")
def test_url_shape_the_adapter_cannot_read_falls_through_to_scraping(mock_client: MagicMock) -> None:
    """"I could not ask the board" must not be reported as "the board said no".

    The board API is never called here because there is no id to call it with,
    so refusing would be a claim the code has no basis for. The page still gets
    its chance.
    """
    mock_client.return_value = _client(
        {"greenhouse.io": _response(text=f"<html><body>{_BODY}</body></html>")},
        landing="https://boards.greenhouse.io/some/unfamiliar/shape",
    )

    assert fetch_posting("https://boards.greenhouse.io/some/unfamiliar/shape").source == "generic"


@patch("services.fetch_posting.httpx.Client")
def test_a_search_page_title_is_refused(mock_client: MagicMock) -> None:
    """The last class of dead link: no 404, no redirect, just the search page.

    Only the page TITLE is examined. One careers site renders its live postings
    inside the same search shell as its dead ones, so their body text is
    identical down to the "jobs matched" count — matching on that would throw
    away every real posting from that employer. The titles differ completely.
    """
    page = "<title>Jobs search — Acme Careers</title><body>" + ("word " * 200) + "</body>"
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=page)},
        landing="https://careers.acme.com/jobs/8052118",
    )

    with pytest.raises(PostingFetchError, match="job search page"):
        fetch_posting("https://careers.acme.com/jobs/8052118")


@patch("services.fetch_posting.httpx.Client")
def test_a_configuration_dump_is_refused(mock_client: MagicMock) -> None:
    """Some careers sites ship their whole theme config as text.

    One returned half a million characters of CSS variables, and its live
    posting and its dead one were near-identical because the description never
    reaches a scraper at all. Truncating that hands the parser thirty thousand
    characters of colour codes to invent a job from.
    """
    dump = "<title>Careers</title><body>" + ('{"color": "#646464", "border": "#111"}' * 400) + "</body>"
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=dump)},
        landing="https://careers.acme.com/jobs/8052118",
    )

    with pytest.raises(PostingFetchError, match="returned its own code"):
        fetch_posting("https://careers.acme.com/jobs/8052118")


@patch("services.fetch_posting.httpx.Client")
def test_a_prose_posting_clears_the_noise_check_comfortably(mock_client: MagicMock) -> None:
    # The margin is the point. Real postings measured under 4 noise characters
    # per thousand and the threshold is 25, so ordinary punctuation in a job
    # description comes nowhere near it.
    page = "<title>Software Engineer Intern</title><body><p>" + ("we build things; " * 150) + "</p></body>"
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text=page)},
        landing="https://careers.acme.com/jobs/8052118",
    )

    assert fetch_posting("https://careers.acme.com/jobs/8052118").source == "generic"


# --- Failure paths -----------------------------------------------------------


@pytest.mark.parametrize("url", [
    "https://www.linkedin.com/jobs/view/1",
    "https://app.joinhandshake.com/jobs/1",
    "https://indeed.com/viewjob?jk=1",
])
def test_known_blocked_hosts_fail_immediately(url: str) -> None:
    # No client patch on purpose: these must be refused before any request, so
    # a test that touched the network here would prove the opposite.
    with pytest.raises(PostingFetchError) as excinfo:
        fetch_posting(url)
    assert "Paste the posting text instead." in str(excinfo.value)


def test_a_non_link_is_refused_without_a_request() -> None:
    with pytest.raises(PostingFetchError, match="does not look like a link"):
        fetch_posting("not a url at all")


@patch("services.fetch_posting.httpx.Client")
def test_javascript_shell_is_a_failure_not_a_thin_success(mock_client: MagicMock) -> None:
    """The quiet failure this service exists to prevent.

    A page that renders in the browser returns almost no text to a script. Left
    unchecked it is a fetch that 'succeeds' and hands the parser a nav bar to
    invent a job from, so it has to be an error instead.
    """
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text="<html><body><div id='root'></div></body></html>")},
        landing="https://careers.acme.com/jobs/1",
    )

    with pytest.raises(PostingFetchError, match="almost no text"):
        fetch_posting("https://careers.acme.com/jobs/1")


@patch("services.fetch_posting.httpx.Client")
def test_oversized_page_is_truncated_rather_than_rejected(mock_client: MagicMock) -> None:
    # One real careers page returned nearly half a million characters of app
    # strings. The posting is at the top, so cut rather than refuse.
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text="<p>" + ("word " * 100_000) + "</p>")},
        landing="https://careers.acme.com/jobs/1",
    )

    result = fetch_posting("https://careers.acme.com/jobs/1")

    assert len(result.text) < 40_000
    assert result.text.endswith("[truncated by the fetcher]")


@patch("services.fetch_posting.httpx.Client")
def test_non_html_response_is_not_scraped(mock_client: MagicMock) -> None:
    # A link to a PDF must not be run through the tag stripper and returned as
    # binary noise dressed up as a posting.
    mock_client.return_value = _client(
        {"careers.acme.com": _response(text="%PDF-1.4 binary", html=False)},
        landing="https://careers.acme.com/job.pdf",
    )

    with pytest.raises(PostingFetchError, match="Could not read that page"):
        fetch_posting("https://careers.acme.com/job.pdf")
