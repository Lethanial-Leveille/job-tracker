"""Tests for the discovery feed's fetch and filter.

The filter is the piece of this feature most likely to break quietly. It cannot
crash — it either keeps a listing or it does not — so a bug here shows up as an
inbox that is emptier than it should be, which looks exactly like a slow week.
That is what these are guarding.

No network: fetch is exercised against a patched client, and every filter test
builds its listings by hand. The live feed was measured separately while writing
the defaults, and the numbers that came out of it are recorded in the module's
comments rather than asserted here — pinning a test to a third party's daily
catalogue would fail for reasons that have nothing to do with this code.
"""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from schemas.discovery import FeedListing
from services.feed import fetch_listings, filter_listings, pull


def _listing(**overrides: object) -> FeedListing:
    """A listing that passes every default check, so each test can break one."""
    base = {
        "id": "abc123",
        "company_name": "Acme",
        "title": "Software Engineer Intern",
        "url": "https://jobs.example.com/1",
        "category": "Software",
        "active": True,
        "is_visible": True,
        "terms": ["Summer 2027"],
        "degrees": ["Bachelor's", "Master's"],
        "date_posted": datetime.now(UTC).timestamp(),
    }
    base.update(overrides)
    return FeedListing(**base)  # type: ignore[arg-type]


# --- Fetching ----------------------------------------------------------------


@patch("services.feed.httpx.get")
def test_a_malformed_entry_is_skipped_not_fatal(mock_get: MagicMock) -> None:
    """One bad entry must not cost the whole night's pull.

    This file is written by someone else and republished daily. Every field on
    FeedListing has a default so that this is rare, and this is the backstop for
    when it happens anyway.
    """
    response = MagicMock()
    response.json.return_value = [
        {"id": "1", "company_name": "Acme", "title": "Intern", "url": "u"},
        "this is not an object at all",
        {"id": "2", "company_name": "Beta", "title": "Intern", "url": "u"},
    ]
    mock_get.return_value = response

    listings = fetch_listings()

    assert [listing.id for listing in listings] == ["1", "2"]


@patch("services.feed.httpx.get")
def test_an_entry_missing_fields_still_loads(mock_get: MagicMock) -> None:
    # The defaults on FeedListing doing their job: a sparse entry becomes a
    # listing that the filter can reject, rather than a validation error.
    response = MagicMock()
    response.json.return_value = [{"id": "1"}]
    mock_get.return_value = response

    listings = fetch_listings()

    assert len(listings) == 1
    assert listings[0].title == ""
    assert listings[0].active is False


# --- Filtering ---------------------------------------------------------------


def test_keeps_a_listing_that_passes_everything() -> None:
    kept, dropped = filter_listings([_listing()])

    assert len(kept) == 1
    assert dropped == {}


def test_category_spelling_variants_are_treated_as_one() -> None:
    """The bug this alias table exists to prevent.

    The feed labels the same category more than one way. Comparing the raw
    string against a single spelling drops the other spelling silently, and a
    filter that quietly discards real postings is indistinguishable from a quiet
    week.
    """
    kept, _ = filter_listings(
        [_listing(category="Software"), _listing(category="Software Engineering")]
    )

    assert len(kept) == 2


def test_an_unrecognized_category_is_counted_under_its_own_label() -> None:
    """A new label the feed invents must be visible, not silent.

    It is still dropped — this is a filter, and keeping unknowns would defeat
    it. But it is counted under the feed's own spelling, so a category that
    appears out of nowhere reads as a number you can act on.
    """
    kept, dropped = filter_listings([_listing(category="Robotics")])

    assert kept == []
    assert dropped == {"category:Robotics": 1}


def test_wrong_term_is_dropped() -> None:
    kept, dropped = filter_listings([_listing(terms=["Summer 2026"])])

    assert kept == []
    assert dropped == {"term": 1}


def test_a_masters_only_posting_is_dropped() -> None:
    # Not a near miss — a different job.
    kept, dropped = filter_listings([_listing(degrees=["Master's", "PhD"])])

    assert kept == []
    assert dropped == {"degree": 1}


def test_a_closed_posting_is_dropped() -> None:
    kept, dropped = filter_listings([_listing(active=False)])

    assert kept == []
    assert dropped == {"closed": 1}


def test_a_listing_with_no_link_is_dropped_as_incomplete() -> None:
    # There is nothing to link to, so this one cannot be rescued by widening
    # any of the other filters.
    kept, dropped = filter_listings([_listing(url="")])

    assert kept == []
    assert dropped == {"incomplete": 1}


def test_an_old_posting_is_dropped() -> None:
    old = (datetime.now(UTC) - timedelta(days=60)).timestamp()

    kept, dropped = filter_listings([_listing(date_posted=old)])

    assert kept == []
    assert dropped == {"stale": 1}


def test_a_missing_post_date_is_kept_not_dropped() -> None:
    """No date is not evidence of being old.

    Discarding a current posting because the feed forgot to say when it went up
    is the more expensive of the two possible mistakes here.
    """
    kept, dropped = filter_listings([_listing(date_posted=None)])

    assert len(kept) == 1
    assert dropped == {}


def test_each_listing_is_counted_under_exactly_one_reason() -> None:
    """Otherwise the tally cannot be read as a breakdown.

    This listing is wrong in three ways at once. Checks run cheapest-first and
    stop at the first failure, so it lands under "closed" alone and the totals
    still add up to the number of listings.
    """
    kept, dropped = filter_listings(
        [_listing(active=False, category="Quant", terms=["Summer 2026"])]
    )

    assert kept == []
    assert sum(dropped.values()) == 1


def test_widening_the_filter_is_one_argument() -> None:
    # The knobs are the whole tuning story, so they need to actually work.
    listings = [_listing(category="Quant")]

    assert filter_listings(listings)[0] == []
    assert len(filter_listings(listings, categories=frozenset({"quant"}))[0]) == 1


# --- pull() ------------------------------------------------------------------


@patch("services.feed.httpx.get")
def test_pull_reports_what_it_saw_and_what_it_discarded(mock_get: MagicMock) -> None:
    response = MagicMock()
    response.json.return_value = [
        json.loads(_listing().model_dump_json()),
        json.loads(_listing(id="x", terms=["Summer 2026"]).model_dump_json()),
    ]
    mock_get.return_value = response

    kept, result = pull()

    assert len(kept) == 1
    assert result.fetched == 2
    assert result.kept == 1
    assert result.dropped == {"term": 1}


@patch("services.feed.httpx.get")
def test_a_failed_download_raises(mock_get: MagicMock) -> None:
    # Deliberately NOT swallowed. A pull that cannot reach the feed has done
    # nothing, and reporting "staged 0" would be indistinguishable from a night
    # with no new postings.
    mock_get.side_effect = httpx.ConnectError("no route to host")

    with pytest.raises(httpx.HTTPError):
        pull()
