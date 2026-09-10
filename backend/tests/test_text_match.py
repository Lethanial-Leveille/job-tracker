"""Tests for the employer/title matching helpers.

These functions are a PORT of frontend/src/lib/dedupe.ts, and the point of this
file is the port staying honest. The frontend groups the pipeline by company and
warns about duplicate adds; the backend decides which application an email
belongs to. If the two drift, the same employer groups one way on screen and
matches another way during ingestion, and nothing visibly breaks — the wrong
suggestion just quietly appears.

Every expected value below was produced by RUNNING the TypeScript over the same
inputs, not by reading it. When you change either side, re-run both.
"""

import pytest

from services.text_match import (
    normalize_organization,
    normalize_url,
    role_similarity,
    role_tokens,
    stem,
    urls_match,
)

# Verified against dedupe.ts output.
ORG_CASES = [
    ("Google, LLC", "google"),
    ("Google", "google"),
    ("The Walt Disney Company", "walt disney"),
    ("Arm", "arm"),
    ("Arm Limited", "arm"),
    ("Microsoft CoreAI", "microsoft coreai"),
    ("C3 AI", "c3 ai"),
    ("O'Reilly & Sons Inc.", "oreilly sons"),
    ("AT&T", "att"),
    ("Ernst & Young", "ernst young"),
    ("3M Co", "3m"),
    ("Booz Allen Hamilton", "booz allen hamilton"),
]


@pytest.mark.parametrize("raw,expected", ORG_CASES)
def test_organization_normalization_matches_the_typescript(
    raw: str, expected: str
) -> None:
    assert normalize_organization(raw) == expected


def test_inconsistent_spellings_of_one_employer_collapse_together() -> None:
    assert normalize_organization("Arm Limited") == normalize_organization("Arm")
    assert normalize_organization("Google, Inc.") == normalize_organization("Google")


def test_genuinely_different_employers_stay_apart() -> None:
    assert normalize_organization("Stripe") != normalize_organization("Square")


# (title a, title b, do they match at the 0.7 threshold) — verified against
# findSimilarPosting in dedupe.ts, which uses the same cutoff.
ROLE_CASES = [
    ("Software Engineer Intern, Summer 2027", "Software Engineering Internship 2027", True),
    ("Data Engineer Intern", "Data Engineering Internship", True),
    ("Software Engineer Intern", "Engineering Intern", True),
    ("Software Engineer Intern / Basketball Operations", "Software Engineer Intern", True),
    ("Test Automation Engineer", "Test Automation Engineers", True),
    ("Business Systems Analyst", "Business Systems Analysts", True),
    ("Software Engineer Intern", "Hardware Engineer Intern", False),
    ("Backend Engineer Intern", "Frontend Engineer Intern", False),
    ("Systems Engineer Intern", "SysEng Software Engineer", False),
    ("not stated", "Intern Program - Engineering Pathways", False),
]


@pytest.mark.parametrize("a,b,expected", ROLE_CASES)
def test_role_similarity_matches_the_typescript(a: str, b: str, expected: bool) -> None:
    assert (role_similarity(a, b) >= 0.7) is expected


def test_stemming_collapses_engineer_and_engineering() -> None:
    """The case that regressed once already in the TypeScript: without stemming
    these share no tokens and score zero, which is the most common way one job
    gets titled two ways."""
    assert stem("engineering") == stem("engineer") == "engine"


def test_short_words_are_not_mangled_into_noise() -> None:
    # Each strip rule needs to leave four characters, so these survive intact.
    assert stem("data") == "data"
    assert stem("ai") == "ai"
    # "ss" is exempt from the plural strip.
    assert stem("business") == "business"


def test_titles_with_no_meaningful_words_score_zero() -> None:
    """A title of pure noise ("Summer Intern 2027") must not match everything by
    having an empty token set. The parser used to emit "not stated" for postings
    with no title, and that has to match nothing rather than anything."""
    assert role_tokens("Summer Intern 2027") == set()
    assert role_similarity("Summer Intern 2027", "Software Engineer Intern") == 0.0


# --- URL matching ------------------------------------------------------------
# Twin of normalizeUrl in dedupe.ts. The whole reason these functions live in
# two languages is that the browser warns you about a duplicate before a parse
# call and the discovery feed drops one server-side — if they disagree, the same
# posting is a repeat in one place and a new job in the other.

URL_CASES: list[tuple[str, str]] = [
    # Scheme, www, case, and trailing slash are all noise.
    ("https://www.Example.com/jobs/1/", "example.com/jobs/1"),
    ("http://example.com/jobs/1", "example.com/jobs/1"),
    # A pasted link often has no scheme at all.
    ("example.com/jobs/1", "example.com/jobs/1"),
    # The fragment is where the browser scrolls to, not which job it is.
    ("https://example.com/jobs/1#apply", "example.com/jobs/1"),
    # Param ORDER must not make one link look like two.
    ("https://example.com/j?b=2&a=1", "example.com/j?a=1&b=2"),
]


@pytest.mark.parametrize("raw,expected", URL_CASES)
def test_normalize_url_matches_the_typescript(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


def test_the_job_id_in_a_query_string_is_never_stripped() -> None:
    """The reason the tracking list is short rather than "drop every param".

    Greenhouse and Lever put the actual job id in the query string. A blanket
    strip would collapse every posting at one company into a single key and
    report constant false duplicates — hiding real jobs, which is the worst
    outcome this feature has.
    """
    assert normalize_url("https://boards.greenhouse.io/x?gh_jid=4055123&utm_campaign=q") == (
        "boards.greenhouse.io/x?gh_jid=4055123"
    )


def test_any_utm_parameter_is_stripped_by_prefix() -> None:
    """Enumerating tracking keys is a losing game.

    The named list missed utm_id on a real posting link, and every miss is a
    duplicate that slips through as a new job. Analytics tools invent utm_
    suffixes freely, so the prefix is the rule and the list is the exception.
    """
    assert normalize_url("https://x.com/j?utm_id=9&utm_whatever=z") == "x.com/j"


def test_a_shared_link_matches_the_one_you_saved() -> None:
    # The real case: a posting shared from a phone carries a Facebook click id,
    # the same posting off the company site does not.
    shared = "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/job/298217?fbclid=PAcG&utm_id=97760"
    plain = "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/careers/job/298217"

    assert urls_match(shared, plain)


def test_different_jobs_at_one_company_stay_different() -> None:
    assert not urls_match("https://x.com/jobs/1", "https://x.com/jobs/2")


def test_something_half_typed_is_compared_not_rejected() -> None:
    # Faithful to the TypeScript, which falls back rather than throwing: you may
    # have pasted something incomplete, and that is not an error worth raising.
    assert normalize_url("  not a url  ") == "not a url"
    assert normalize_url("   ") is None
