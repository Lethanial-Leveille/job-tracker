"""Tests for the graduation-eligibility check.

Two failure modes matter here and they are not symmetric.

Telling you a job is out of reach when it is not costs you an application you
would have won. Staying quiet when a posting really does exclude you costs you
an application you were never eligible for. The first is worse, which is why
"unclear" is the default answer and why a year has to sit next to a word about
graduating before it counts for anything.

Pure functions, no network, no database.
"""

import pytest

from schemas.resume import Contact, Education, Resume
from services.eligibility import assess, graduation_years

MINE = [2028, 2029]


# --- Reading your own dates --------------------------------------------------


def test_both_graduation_dates_are_read() -> None:
    """A student with two true graduation dates has two.

    Reading only the primary would report a posting wanting the later year as a
    mismatch, when taking the extra year is a choice already on the resume.
    """
    resume = Resume(
        contact=Contact(name="Lee"),
        education=[
            Education(
                institution="UF",
                degree="BS Computer Engineering",
                dates="Expected May 2028",
                dates_alternate="Expected May 2029",
            )
        ],
    )

    assert graduation_years(resume) == [2028, 2029]


def test_a_resume_with_no_education_yields_nothing() -> None:
    assert graduation_years(Resume(contact=Contact(name="Lee"))) == []


# --- The verdict -------------------------------------------------------------


def test_a_year_you_can_claim_is_eligible() -> None:
    result = assess("Must be graduating in the Class of 2028.", [], MINE)

    assert result.verdict == "eligible"
    assert result.wanted_years == [2028]
    assert "Class of 2028" in result.evidence


def test_a_year_you_cannot_claim_is_a_mismatch() -> None:
    result = assess("Open to students graduating in 2026.", [], MINE)

    assert result.verdict == "mismatch"
    assert result.wanted_years == [2026]


def test_a_range_is_treated_as_a_span_not_two_points() -> None:
    """"Graduating between December 2027 and June 2029" includes 2028.

    Reading the years as the set {2027, 2029} would report a mismatch for
    someone graduating in the middle of the window the posting explicitly
    describes.
    """
    result = assess(
        "You will be graduating between December 2027 and June 2029.", [], [2028]
    )

    assert result.verdict == "eligible"


def test_a_year_with_nothing_to_do_with_graduating_is_ignored() -> None:
    """The check that stops this producing confident nonsense.

    Every posting is full of years — the term it is for, a start date, a product
    roadmap. Only a year sitting beside a word about graduating means anything.
    """
    result = assess("This is our Summer 2027 internship program.", [], MINE)

    assert result.verdict == "unclear"
    assert result.wanted_years == []


def test_silence_is_unclear_not_a_rejection() -> None:
    # The common case. Most postings say nothing, and reporting that as a
    # problem would train you to ignore the field.
    result = assess("Build backend services with a great team.", [], MINE)

    assert result.verdict == "unclear"
    assert result.evidence is None


def test_the_raw_posting_outranks_the_parsed_requirements() -> None:
    """The false mismatch this ordering exists to prevent, from a real posting.

    A Dell listing said "a graduation date of December 2027 through 2028". The
    parser summarised that as the single phrase "December 2027", and checking
    requirements first reported a 2028 graduate as ineligible — a job lost to a
    paraphrase. The employer's own words win.
    """
    result = assess(
        "Enrolled in an undergraduate degree with a graduation date of December 2027 through 2028.",
        ["Graduating December 2027"],
        [2028],
    )

    assert result.verdict == "eligible"
    assert result.wanted_years == [2027, 2028]


def test_years_named_in_two_places_are_pooled_into_one_window() -> None:
    """A posting that states its window twice must not be judged on half of it.

    Reading only the first graduation sentence is how a range gets truncated,
    and a truncated range is the difference between applying and not.
    """
    result = assess(
        "Class of 2027 preferred. Candidates graduating as late as 2029 are welcome.",
        [],
        [2028],
    )

    assert result.verdict == "eligible"
    assert result.wanted_years == [2027, 2029]


def test_the_quoted_sentence_is_the_one_carrying_the_window() -> None:
    # A verdict about a range quoted against a sentence naming one year is
    # evidence you cannot check.
    result = assess(
        "Graduating in 2027. Specifically, graduation between 2027 and 2029.",
        [],
        [2028],
    )

    assert "2027 and 2029" in result.evidence


def test_requirements_still_count_when_the_body_is_silent() -> None:
    # The fallback is a fallback, not dead code: a posting read from a job
    # board's API can arrive as structured fields with little prose.
    result = assess("", ["Must be graduating in the Class of 2026"], [2028, 2029])

    assert result.verdict == "mismatch"


def test_class_standing_is_reported_but_never_judged() -> None:
    """Deliberate restraint.

    Whether "rising senior" includes you depends on your credit hours at a date
    a year away, which this module would be guessing at. Surfacing the sentence
    lets you decide in two seconds; guessing would be wrong quietly.
    """
    result = assess("Open to rising seniors with strong fundamentals.", [], MINE)

    assert result.verdict == "unclear"
    assert result.standing is not None
    assert "rising seniors" in result.standing


def test_standing_travels_alongside_a_year_verdict() -> None:
    # Both signals are useful and they are not alternatives.
    result = assess(
        "Open to rising juniors. Must be graduating in 2026.", [], MINE
    )

    assert result.verdict == "mismatch"
    assert result.standing is not None


def test_no_dates_of_your_own_means_unclear_not_a_guess() -> None:
    # There is nothing to compare against, so there is no verdict to give.
    result = assess("Must be graduating in 2026.", [], [])

    assert result.verdict == "unclear"
    assert result.wanted_years == [2026]


@pytest.mark.parametrize(
    "text",
    [
        "Class of 2028 candidates preferred.",
        "Expected graduation: May 2028.",
        "Degree completion in 2028 required.",
    ],
)
def test_the_phrases_that_count_as_graduation_context(text: str) -> None:
    # Twin of GRAD_CONTEXT in gradHint.ts — these must stay in step, or a
    # posting reads one way in the browser and another on the server.
    assert assess(text, [], MINE).verdict == "eligible"
