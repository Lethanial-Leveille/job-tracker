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
    role_similarity,
    role_tokens,
    stem,
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
