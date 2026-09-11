"""Tests for reading a whole job board from each of the five systems.

Every vendor quirk pinned here cost real time to find, and each one fails
SILENTLY rather than loudly — a wrong page size, a missing query parameter, or a
mis-built URL all produce an empty list or a dead link, which look exactly like
a company with no open roles. That is the failure mode these guard against.

No network: each reader is exercised against a fake client returning the shape
that vendor actually sent when I ran it live.
"""

from unittest.mock import MagicMock, patch

import httpx

from services.boards import (
    _WORKDAY_PAGE,
    BoardPosting,
    ashby,
    greenhouse,
    lever,
    oracle,
    read_board,
    workday,
)


def _client(payload: object, *, status: int = 200) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    client.request.return_value = response
    return client


# --- The three that were already half-written --------------------------------


def test_greenhouse_reads_a_board() -> None:
    client = _client(
        {
            "jobs": [
                {
                    "id": 8172510,
                    "title": "Software Engineer Intern",
                    "absolute_url": "https://boards.greenhouse.io/stripe/jobs/8172510",
                    "location": {"name": "Seattle"},
                    "first_published": "2026-09-03T10:00:00Z",
                }
            ]
        }
    )

    postings = greenhouse(client, "stripe")

    assert postings == [
        BoardPosting(
            external_id="8172510",
            title="Software Engineer Intern",
            url="https://boards.greenhouse.io/stripe/jobs/8172510",
            location="Seattle",
            posted_at=__import__("datetime").date(2026, 9, 3),
        )
    ]


def test_greenhouse_does_not_ask_for_every_description() -> None:
    """The full text of every role at a company is megabytes thrown away.

    Enrichment fetches the one posting you care about later, and only for jobs
    that survived filtering. Asking here would make a board read enormous for no
    gain.
    """
    client = _client({"jobs": []})

    greenhouse(client, "stripe")

    _, kwargs = client.request.call_args
    assert "content" not in (kwargs.get("params") or {})


def test_lever_reads_milliseconds_not_an_iso_string() -> None:
    # Lever is the only one of the five that dates a posting in epoch
    # milliseconds. Parsed as seconds it lands in 1970 and sorts to the bottom
    # forever.
    client = _client(
        [
            {
                "id": "abc",
                "text": "Backend Intern",
                "hostedUrl": "https://jobs.lever.co/acme/abc",
                "categories": {"location": "Remote"},
                "createdAt": 1787000000000,
            }
        ]
    )

    postings = lever(client, "acme")

    assert postings[0].posted_at is not None
    assert postings[0].posted_at.year > 2020


def test_ashby_reads_a_board() -> None:
    client = _client(
        {"jobs": [{"id": "u-1", "title": "SWE Intern", "jobUrl": "https://jobs.ashbyhq.com/acme/u-1"}]}
    )

    assert ashby(client, "acme")[0].external_id == "u-1"


# --- The two that had to be written from scratch -----------------------------


def test_workday_pages_because_it_caps_a_page_at_twenty() -> None:
    """Asking Workday for 50 returns a 400 with an empty message.

    That is a memorable way to spend twenty minutes, and it is why this reader
    pages where the others ask once.
    """
    client = MagicMock()
    full = MagicMock()
    full.status_code = 200
    full.json.return_value = {
        "jobPostings": [
            {"title": f"Intern {i}", "externalPath": f"/job/X/R{i}", "bulletFields": [f"R{i}"]}
            for i in range(_WORKDAY_PAGE)
        ]
    }
    last = MagicMock()
    last.status_code = 200
    last.json.return_value = {"jobPostings": []}
    client.request.side_effect = [full, last]

    postings = workday(client, "acme.wd5.myworkdayjobs.com", "acme", "external")

    assert len(postings) == _WORKDAY_PAGE
    # Every request must stay within the cap, or the whole page 400s.
    for call in client.request.call_args_list:
        assert call.kwargs["json"]["limit"] <= _WORKDAY_PAGE


def test_workday_rebuilds_a_usable_link_from_a_relative_path() -> None:
    """Workday returns "/job/San-Jose/..." — a path, not a URL.

    Built against the API path instead of the public site, every posting links
    somewhere that 404s, and nothing downstream would notice until you clicked
    one.
    """
    client = _client(
        {"jobPostings": [{"title": "Intern", "externalPath": "/job/San-Jose/R1", "bulletFields": ["R1"]}]}
    )

    postings = workday(client, "acme.wd5.myworkdayjobs.com", "acme", "external_experienced")

    assert postings[0].url == (
        "https://acme.wd5.myworkdayjobs.com/external_experienced/job/San-Jose/R1"
    )


def test_workday_survives_a_posting_with_no_requisition_id() -> None:
    # bulletFields is occasionally empty, and indexing it blindly ends the whole
    # company's read on one odd row.
    client = _client(
        {"jobPostings": [{"title": "Intern", "externalPath": "/job/X/R1", "bulletFields": []}]}
    )

    assert workday(client, "h", "t", "s")[0].external_id == "/job/X/R1"


def test_oracle_asks_for_the_expansion_that_carries_the_jobs() -> None:
    """Without `expand`, Oracle answers 200 with facets and counts and NO jobs.

    The reader then returns nothing and the company looks like it has no open
    roles. A silent 200 is the worst possible shape for this mistake.
    """
    client = _client({"items": [{"requisitionList": []}]})

    oracle(client, "careers.acme.com", "CX_1001")

    _, kwargs = client.request.call_args
    assert "requisitionList" in kwargs["params"]["expand"]


def test_oracle_reads_jobs_from_one_level_down() -> None:
    # The rows are inside items[0].requisitionList, not in items itself.
    client = _client(
        {
            "items": [
                {
                    "requisitionList": [
                        {"Id": "R1", "Title": "Intern", "PrimaryLocation": "TX", "PostedDate": "2026-09-01"}
                    ]
                }
            ]
        }
    )

    postings = oracle(client, "careers.acme.com", "CX_1001")

    assert postings[0].external_id == "R1"
    assert postings[0].url.endswith("/sites/CX_1001/job/R1")


def test_oracle_handles_an_empty_response_without_indexing_into_nothing() -> None:
    assert oracle(_client({"items": []}), "h", "CX_1") == []


# --- The internship gate -----------------------------------------------------
# A board carries every open role at the company and internships are a small
# minority — Stripe's had 620 jobs and 7 internships. The aggregator feed needed
# none of this because it is an internships-only list; a company board is not,
# and that is the biggest difference between the two sources.


def test_a_board_full_of_senior_roles_yields_no_internships() -> None:
    """The bug that got all the way to a live run.

    Every family the classifier knows ends in "Intern", so handed "Engineering
    Manager" it picks the nearest one and a senior full-time role lands in the
    inbox looking like a match. It cannot say "this is not an internship", so
    the title has to.
    """
    client = _client(
        {
            "jobs": [
                {"id": 1, "title": "Engineering Manager, Payments", "absolute_url": "u"},
                {"id": 2, "title": "Enterprise Account Executive", "absolute_url": "u"},
            ]
        }
    )

    assert greenhouse(client, "acme") == []


def test_the_gate_is_word_bounded() -> None:
    """"Internal" and "International" are most of a large company's postings.

    A bare prefix match on "intern" would let every one of them through, which
    is worse than no filter at all — it would look like the filter was working.
    """
    from services.boards import is_internship

    assert not is_internship("Internal Audit Manager")
    assert not is_internship("International Tax Director")
    assert is_internship("Software Engineer Intern")
    assert is_internship("Engineering Co-op, Summer 2027")
    assert is_internship("Hardware Internship Program")


def test_the_cap_applies_after_filtering_not_before() -> None:
    """Capping first is how you read 100 senior roles and conclude a company has
    no internships.

    Greenhouse has no server-side search, so the whole board comes back with the
    internships scattered through it.
    """
    jobs = [{"id": i, "title": "Director of Sales", "absolute_url": "u"} for i in range(300)]
    jobs.append({"id": 999, "title": "Software Engineer Intern", "absolute_url": "u"})

    postings = greenhouse(_client({"jobs": jobs}), "acme")

    assert [p.external_id for p in postings] == ["999"]


def test_vendor_search_is_sent_but_not_trusted() -> None:
    """Workday returns "Product Manager - International Strategy" for "intern".

    The search term is worth sending to narrow what comes back. It is not worth
    believing, so the title still decides.
    """
    client = _client(
        {
            "jobPostings": [
                {"title": "Product Manager - International Strategy", "externalPath": "/job/X/1", "bulletFields": ["1"]},
                {"title": "2027 Intern - Software Engineer", "externalPath": "/job/X/2", "bulletFields": ["2"]},
            ]
        }
    )

    postings = workday(client, "h", "t", "s")

    assert [p.external_id for p in postings] == ["2"]
    assert client.request.call_args.kwargs["json"]["searchText"] == "intern"


# --- Failure and politeness --------------------------------------------------


def test_a_non_200_yields_no_postings_rather_than_an_exception() -> None:
    # One unreachable company must not end a run that has four others to do.
    assert greenhouse(_client({}, status=503), "acme") == []


def test_a_transport_failure_yields_no_postings() -> None:
    client = MagicMock()
    client.request.side_effect = httpx.ConnectError("no route")

    assert lever(client, "acme") == []


def test_an_unknown_system_reads_nothing_instead_of_guessing() -> None:
    assert read_board("workable", None, "acme", None) == []


@patch("services.boards.time.sleep")
@patch("services.boards.httpx.Client")
def test_requests_to_one_vendor_are_spaced(
    mock_client: MagicMock, mock_sleep: MagicMock
) -> None:
    """These are other people's servers, polled nightly with no arrangement.

    The right shape is a trickle rather than a burst. Two reads of the same
    vendor back to back must wait between them.
    """
    client = _client({"jobs": []})
    client.__enter__.return_value = client
    mock_client.return_value = client

    read_board("greenhouse", None, "acme", None)
    read_board("greenhouse", None, "beta", None)

    assert mock_sleep.called


# --- Identifying a board from a link -----------------------------------------
# So that adding a company is pasting a link rather than knowing that Stripe's
# Greenhouse token is "stripe". Getting one of those wrong produces a watchlist
# entry that returns nothing every night without saying why.


def test_a_greenhouse_board_link_is_recognised() -> None:
    from services.boards import identify

    assert identify("https://boards.greenhouse.io/stripe") == {
        "ats": "greenhouse",
        "host": None,
        "board": "stripe",
        "site": None,
    }


def test_a_greenhouse_embed_link_carries_the_board_in_the_query() -> None:
    # The embed form is roughly one in ten Greenhouse links and puts the board
    # in a parameter rather than the path.
    from services.boards import identify

    found = identify("https://job-boards.greenhouse.io/embed/job_app?for=coinbase&token=1")

    assert found == {"ats": "greenhouse", "host": None, "board": "coinbase", "site": None}


def test_a_workday_link_yields_all_three_identifiers() -> None:
    """The tenant comes from the HOSTNAME, not the path.

    "adobe" from "adobe.wd5.myworkdayjobs.com". Reading it out of the path
    instead gives the site id twice and a board that never answers.
    """
    from services.boards import identify

    assert identify("https://adobe.wd5.myworkdayjobs.com/en-US/external_experienced") == {
        "ats": "workday",
        "host": "adobe.wd5.myworkdayjobs.com",
        "board": "adobe",
        "site": "external_experienced",
    }


def test_a_workday_link_without_a_locale_still_parses() -> None:
    from services.boards import identify

    found = identify("https://acme.wd1.myworkdayjobs.com/careers")

    assert found is not None and found["site"] == "careers"


def test_an_oracle_link_is_matched_on_its_path() -> None:
    """Oracle is hosted per employer, so its hostname says nothing.

    Dell serves from enterpriseplatform.dell.com. A host-based check would never
    reach it, which is why this one is matched on the path.
    """
    from services.boards import identify

    found = identify(
        "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/298217"
    )

    assert found == {
        "ats": "oracle",
        "host": "enterpriseplatform.dell.com",
        "board": None,
        "site": "CX_1001",
    }


def test_a_company_on_its_own_careers_site_is_not_one_of_the_five() -> None:
    """A normal answer, not a failure.

    Plenty of employers run their own careers site and simply cannot be polled
    directly — those only ever come from the aggregator feed.
    """
    from services.boards import identify

    assert identify("https://careers.google.com/jobs") is None
    assert identify("   ") is None
