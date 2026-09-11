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
from services.eligibility import assess, graduation_dates

# Lee's two real graduation dates, months included: the month is what the
# too-early rule turns on.
MINE = [(2028, 5), (2029, 5)]


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

    assert graduation_dates(resume) == [(2028, 5), (2029, 5)]


def test_a_resume_with_no_education_yields_nothing() -> None:
    assert graduation_dates(Resume(contact=Contact(name="Lee"))) == []


# --- The verdict -------------------------------------------------------------


def test_your_own_graduation_year_is_plainly_eligible() -> None:
    result = assess("Must be graduating in 2029.", [], MINE)

    assert result.verdict == "eligible"
    assert result.wanted_years == [2029]
    assert "2029" in result.evidence


def test_a_posting_wanting_your_earlier_date_is_flagged_not_rejected() -> None:
    """The state that stops a real job being thrown away.

    You have two true graduation dates. A posting wanting the Class of 2028
    when you are on track for 2029 is not a rejection — it is a prompt to claim
    the earlier one, which is a decision with consequences for the rest of the
    resume. Calling it "mismatch" loses a job you can have; calling it plain
    "eligible" hides that a choice is being made for you.
    """
    result = assess("Must be graduating in the Class of 2028.", [], MINE)

    assert result.verdict == "eligible_early"
    assert result.wanted_years == [2028]


def test_the_later_date_is_the_default_self() -> None:
    # Taking the full degree is the plan; finishing early is an option you can
    # exercise, not one you are already committed to.
    assert assess("Graduating 2029.", [], MINE).verdict == "eligible"
    assert assess("Graduating 2028.", [], MINE).verdict == "eligible_early"


def test_a_window_that_closes_before_you_finish_is_too_early() -> None:
    """The state that never reaches the inbox.

    A posting wanting 2026 graduates is a new-grad role or a cycle already gone.
    There is nothing to decide, so services/discovery.py drops it rather than
    handing you a row whose only available action is dismiss.
    """
    result = assess("Open to students graduating in 2026.", [], MINE)

    assert result.verdict == "too_early"
    assert result.wanted_years == [2026]


def test_a_window_that_opens_after_you_finish_is_shown_not_hidden() -> None:
    # Rare, and usually an error in the posting rather than a real requirement,
    # which is exactly why it is worth seeing rather than silently dropping.
    result = assess("For students graduating in 2031.", [], MINE)

    assert result.verdict == "too_late"


def test_a_range_is_treated_as_a_span_not_two_points() -> None:
    """"Graduating between December 2027 and June 2029" includes 2028.

    Reading the years as the set {2027, 2029} would report a mismatch for
    someone graduating in the middle of the window the posting explicitly
    describes.
    """
    result = assess(
        "You will be graduating between December 2027 and June 2029.", [], [(2028, 5)]
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
        [(2028, 5)],
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
        [(2028, 5)],
    )

    assert result.verdict == "eligible"
    assert result.wanted_years == [2027, 2029]


def test_the_quoted_sentence_is_the_one_carrying_the_window() -> None:
    # A verdict about a range quoted against a sentence naming one year is
    # evidence you cannot check.
    result = assess(
        "Graduating in 2027. Specifically, graduation between 2027 and 2029.",
        [],
        [(2028, 5)],
    )

    assert "2027 and 2029" in result.evidence


def test_requirements_still_count_when_the_body_is_silent() -> None:
    # The fallback is a fallback, not dead code: a posting read from a job
    # board's API can arrive as structured fields with little prose.
    result = assess("", ["Must be graduating in the Class of 2026"], [(2028, 5), (2029, 5)])

    assert result.verdict == "too_early"


def test_a_posting_naming_only_a_standing_says_nothing_at_all() -> None:
    """Silence beats a chip that means "go read it yourself".

    Whether "rising senior" includes you depends on credit hours at a date a
    year away, which this module would be guessing at. The phrase is still
    carried on the object for anything that wants it, but the verdict stays
    unclear so the inbox shows nothing — a warning that appears on half your
    rows is one you stop reading.
    """
    result = assess("Open to rising seniors with strong fundamentals.", [], MINE)

    assert result.verdict == "unclear"
    assert result.standing is not None


def test_standing_travels_alongside_a_year_verdict() -> None:
    # Both signals are useful and they are not alternatives.
    result = assess(
        "Open to rising juniors. Must be graduating in 2026.", [], MINE
    )

    assert result.verdict == "too_early"
    assert result.standing is not None


def test_no_dates_of_your_own_means_unclear_not_a_guess() -> None:
    # There is nothing to compare against, so there is no verdict to give.
    result = assess("Must be graduating in 2026.", [], [])

    assert result.verdict == "unclear"
    assert result.wanted_years == [2026]


@pytest.mark.parametrize(
    "text",
    [
        "Class of 2029 candidates preferred.",
        "Expected graduation: May 2029.",
        "Degree completion in 2029 required.",
    ],
)
def test_the_phrases_that_count_as_graduation_context(text: str) -> None:
    # Twin of GRAD_CONTEXT in gradHint.ts — these must stay in step, or a
    # posting reads one way in the browser and another on the server. Each
    # phrase must be enough on its own to make the year beside it count.
    assert assess(text, [], MINE).verdict == "eligible"


# --- Months ------------------------------------------------------------------
# The too-early rule is the ONLY comparison that reads months, because it is the
# only verdict that removes a job from view entirely. Everything else stays on
# years, where the extra precision would buy nothing and could only add false
# negatives.


def test_january_2028_is_too_early_for_a_may_2028_graduate() -> None:
    """The gap a year-only check let through.

    January 2028 and December 2028 are a full academic year apart and fall on
    opposite sides of anyone finishing in May. Compared as bare years they are
    the same thing, and a posting that closed a term before you finish reaches
    the inbox looking like an option.
    """
    assert assess("Must graduate by January 2028.", [], MINE).verdict == "too_early"


def test_december_2028_is_still_within_reach() -> None:
    assert assess("Graduating December 2028.", [], MINE).verdict == "eligible_early"


def test_a_bare_year_is_read_generously_as_december() -> None:
    """A posting saying only "2028" might well mean the end of it.

    Reading it as January would rule out a job that is actually open to you, and
    a false "too early" is the expensive error — it removes the row entirely,
    so you never get the chance to disagree.
    """
    assert assess("Class of 2028.", [], MINE).verdict == "eligible_early"


def test_your_own_month_is_read_from_the_resume() -> None:
    # Someone finishing in December 2028 clears a January 2028 posting by no
    # sensible reading, but someone who finished the previous December would.
    december = [(2027, 12)]

    assert assess("Must graduate by January 2028.", [], december).verdict != "too_early"


# --- Degree level ------------------------------------------------------------
# The feed's own degree data lists Bachelor's for postings whose text says
# "currently pursuing an MS or PhD". Only reading the posting catches that, and
# an internship you cannot hold is worse than no result.


def test_a_posting_demanding_a_graduate_degree_is_caught() -> None:
    from services.eligibility import requires_a_graduate_degree

    assert requires_a_graduate_degree(
        ["Currently pursuing a Master's or PhD in Computer Science"], ""
    )


def test_a_list_of_accepted_degrees_is_not_a_graduate_requirement() -> None:
    """The most common phrasing in a real posting, and the one that matters.

    "Bachelor's, Master's or PhD in Computer Science" says what they accept.
    Reading it as a graduate requirement would discard most of the inbox.
    """
    from services.eligibility import requires_a_graduate_degree

    assert requires_a_graduate_degree(
        ["Bachelor's, Master's or PhD in Computer Science"], ""
    ) is None


def test_a_degree_mentioned_in_passing_is_not_a_requirement() -> None:
    # A posting's body talks about degrees constantly. "Our team holds advanced
    # degrees" is a fact about them, not a rule for you, which is why the
    # requirements list is checked first.
    from services.eligibility import requires_a_graduate_degree

    assert requires_a_graduate_degree([], "Our team holds advanced degrees including PhDs.") is None


def test_the_sentence_is_returned_so_a_wrong_call_can_be_argued_with() -> None:
    # These rows vanish from the inbox, so the reason has to survive with them.
    from services.eligibility import requires_a_graduate_degree

    evidence = requires_a_graduate_degree(["Must be a PhD candidate"], "")

    assert evidence is not None and "PhD candidate" in evidence
