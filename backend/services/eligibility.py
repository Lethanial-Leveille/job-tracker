"""Does this posting's graduation requirement rule you out?

The question a job board never answers directly and you would otherwise check by
hand on every posting: it says "Class of 2028" and you need to know whether that
includes you.

A DELIBERATE PORT of the detection half of frontend/src/lib/gradHint.ts, and the
same warning applies — the phrases and the year pattern have a twin in
TypeScript and the two must agree. What differs is the QUESTION. gradHint asks
which of two graduation dates to print on a resume; this asks whether either one
clears the bar. Same evidence, opposite direction, so the detection is shared
and the conclusion is not.

Three answers, and "unclear" is the common one. Most postings say nothing about
graduation timing, and silence is not a rejection — reporting it as one would
train you to ignore the field entirely.
"""

import re
from typing import Literal

from pydantic import BaseModel

from schemas.resume import Resume

# A graduation year only means something next to a word about graduating. A
# posting mentions plenty of other years — the term it is for, a program start
# date, a fiscal year — and matching any stray 2028 would produce confident
# nonsense. Twin of GRAD_CONTEXT in gradHint.ts.
_GRAD_CONTEXT = re.compile(r"(graduat|commencement|degree completion|class of)", re.I)
_YEAR = re.compile(r"\b(20(?:2[5-9]|3[0-2]))\b")

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

# A year, optionally preceded by a month name. The month is what separates a
# posting wanting January 2028 graduates from one wanting December 2028 — a full
# academic year apart, and on opposite sides of anyone finishing in May.
_DATED_YEAR = re.compile(
    r"(?:\b(" + "|".join(_MONTHS) + r")\b[,\s]+)?\b(20(?:2[5-9]|3[0-2]))\b", re.I
)


def _dates_in(text: str) -> list[tuple[int, int | None]]:
    """Every (year, month) a string names. Month is None when it is not stated."""
    found: list[tuple[int, int | None]] = []
    for month, year in _DATED_YEAR.findall(text):
        found.append((int(year), _MONTHS[month.lower()] if month else None))
    return found


def _latest(dates: list[tuple[int, int | None]]) -> tuple[int, int]:
    """The end of a window. A bare year is read as DECEMBER.

    Generous on purpose: a posting that says only "2028" might well mean the end
    of it, and reading it as January would rule out a job that is actually open
    to you. False "too early" is the expensive error.
    """
    return max((year, month if month is not None else 12) for year, month in dates)


def _earliest(dates: list[tuple[int, int | None]]) -> tuple[int, int]:
    """The start of a window. A bare year is read as JANUARY, same reasoning."""
    return min((year, month if month is not None else 1) for year, month in dates)

# Phrases that name a class standing rather than a year. These are REPORTED but
# never turned into a verdict, and the restraint is deliberate: whether "rising
# senior" includes you depends on your credit hours at a date a year out, which
# this module would be guessing at. Surfacing the sentence lets you judge it in
# two seconds; guessing would be wrong quietly.
_STANDING = (
    "rising junior", "rising senior", "junior standing", "senior standing",
    "juniors and seniors", "third year", "fourth year", "penultimate year",
    "final year", "rising sophomore", "sophomore standing", "first year",
    "second year", "freshmen and sophomores", "underclassmen",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;\n])\s+")


class Eligibility(BaseModel):
    """What a posting says about graduation timing, and what it means for you.

    `evidence` is the sentence that produced the verdict, always. A verdict you
    cannot check is one you either obey blindly or ignore, and both are worse
    than no verdict — the same rule gradHint.ts follows for its suggestions.
    """

    # "too_early" and "too_late" are both mismatches and they are not the same
    # problem. Too early means the posting closed before you finish — a new-grad
    # role, or a cycle already gone — and there is nothing you can do about it,
    # so those never reach the inbox at all. Too late means it wants people who
    # graduate after you do, which is rare, strange, and worth seeing.
    verdict: Literal[
        "eligible", "eligible_early", "too_early", "too_late", "unclear"
    ]
    # The years the posting names, if any. Empty for a standing-only or silent
    # posting.
    wanted_years: list[int] = []
    # Your graduation years, echoed back so the UI can say "wants 2026, you are
    # 2028 or 2029" without going and looking them up.
    your_years: list[int] = []
    evidence: str | None = None
    # A class-standing phrase found in the posting ("open to rising seniors").
    # Carried alongside a verdict as extra context, never used to produce one:
    # whether a standing includes you depends on credit hours at a date a year
    # out, which this module would be guessing at. A posting that says ONLY this
    # stays "unclear" and shows nothing, because a chip that appears on half
    # your inbox saying "read the posting" is a chip you stop reading.
    standing: str | None = None


def graduation_dates(resume: Resume) -> list[tuple[int, int | None]]:
    """Every date this person could honestly claim to graduate, month included.

    Reads both `dates` and `dates_alternate` on each school, because a student
    with two true graduation dates has two, and eligibility against either one
    is eligibility.

    The month matters. "Expected May 2028" against a posting wanting January
    2028 graduates is not a match, and a year-only comparison calls it one.
    """
    found: list[tuple[int, int | None]] = []
    for school in resume.education:
        for value in (school.dates, school.dates_alternate):
            if value:
                found.extend(_dates_in(value))
    return sorted(set(found))


def _excerpt(sentence: str, limit: int = 140) -> str:
    """Trim to something that fits a line without losing the part that matters."""
    flat = re.sub(r"\s+", " ", sentence).strip()
    return flat if len(flat) <= limit else f"{flat[: limit - 1]}…"


def assess(
    posting_text: str,
    requirements: list[str],
    your_dates: list[tuple[int, int | None]],
) -> Eligibility:
    """Judge a posting's graduation requirement against your own dates.

    The RAW POSTING TEXT is authoritative and the parsed requirements are only a
    fallback. That ordering is the opposite of what it should intuitively be,
    and it was written the other way round first, which produced a real false
    mismatch: a Dell posting reading "a graduation date of December 2027 through
    2028" came back from the parser as the single phrase "December 2027", and
    the check reported a candidate graduating in 2028 as ineligible. The
    requirements list is a paraphrase; a paraphrase is free to drop half a
    range, and half a range is the difference between applying and not.

    Every graduation sentence is consulted, not just the first, and the years
    they name are pooled into ONE span. A posting that mentions its window in
    two places must not be judged on whichever half was seen first.

    The asymmetry drives all of this. Telling you a job is out of reach when it
    is not costs you an application you would have won; staying quiet when it
    really does exclude you costs an application you were never eligible for.
    So where the evidence is ambiguous, this widens rather than narrows.

    With no graduation years of your own on file, the answer is "unclear" rather
    than a guess. There is nothing to compare against.
    """
    # Verbatim text first: it is what the employer actually wrote.
    sources = [*(_SENTENCE_SPLIT.split(posting_text or "")), *requirements]

    standing = None
    for raw in sources:
        lowered = raw.lower()
        for phrase in _STANDING:
            if phrase in lowered:
                standing = _excerpt(raw)
                break
        if standing:
            break

    dated: list[tuple[int, int | None]] = []
    evidence: str | None = None
    best = 0
    for raw in sources:
        if not _GRAD_CONTEXT.search(raw):
            continue
        here = _dates_in(raw)
        if not here:
            continue
        dated.extend(here)
        # Quote the sentence that named the most dates — it is the one carrying
        # the full window, and a truncated quote next to a verdict about ranges
        # is exactly the evidence you cannot check.
        if len(here) > best:
            best, evidence = len(here), _excerpt(raw)

    if dated:
        span = sorted({year for year, _ in dated})
        your_years = sorted({year for year, _ in your_dates})
        if not your_dates:
            return Eligibility(
                verdict="unclear",
                wanted_years=span,
                evidence=evidence,
                standing=standing,
            )

        # Your LATEST graduation year is the default self. Taking the full
        # degree is the plan; finishing early is the option you can exercise,
        # not the one you are already committed to.
        default_year = max(your_years)
        in_span = lambda year: span[0] <= year <= span[-1]  # noqa: E731

        # The one comparison that uses months. A posting wanting January 2028
        # graduates and one wanting December 2028 are a full academic year
        # apart and fall on opposite sides of anyone finishing in May — a
        # year-only check calls them the same thing and lets the first through.
        #
        # Only "too early" is judged this finely, because it is the only verdict
        # that removes a job from view entirely. The rest stay on years, where
        # the extra precision would buy nothing and could only add false
        # negatives.
        window_closes = _latest(dated)
        you_start = _earliest(your_dates)

        if in_span(default_year):
            verdict = "eligible"
        elif window_closes < you_start:
            # The whole window closes before you can finish. A new-grad posting,
            # or a cycle that has already gone. Nothing to decide and nothing to
            # do, so services/discovery.py keeps these out of the inbox entirely
            # rather than showing you a row you can only dismiss.
            verdict = "too_early"
        elif span[0] > max(your_years):
            # Wants people finishing after you do. Rare and usually a mistake in
            # the posting, so it is surfaced rather than hidden.
            verdict = "too_late"
        elif any(in_span(year) for year in your_years):
            # The distinction worth having. A posting wanting the Class of 2028
            # when you are a 2029 is not a rejection — it is a prompt to claim
            # the earlier of your two true graduation dates, which is a real
            # decision with real consequences for the rest of the resume.
            # Reporting it as "too early" would throw away a job you can have;
            # reporting it as plain "eligible" would hide that a choice is
            # being made on your behalf.
            verdict = "eligible_early"
        else:
            # Your dates straddle a gap the window falls into — possible only
            # with a non-contiguous set of graduation dates, and not something
            # to guess about.
            verdict = "too_early"

        return Eligibility(
            verdict=verdict,
            wanted_years=span,
            your_years=your_years,
            evidence=evidence,
            standing=standing,
        )

    # Silent about graduation timing, which is the usual case and not a problem.
    return Eligibility(
        verdict="unclear",
        your_years=sorted({year for year, _ in your_dates}),
        standing=standing,
    )


# --- Degree level -------------------------------------------------------------

# A requirement that rules out an undergraduate. The feed's own degree data is
# frequently wrong about this — it lists Bachelor's for postings whose text says
# "currently pursuing an MS or PhD" — and only reading the posting catches it.
_GRADUATE_ONLY = re.compile(
    r"(currently\s+(?:enrolled|pursuing)[^.]{0,60}\b(?:master|m\.?s\.?|phd|ph\.?d\.?|doctora)"
    r"|\b(?:master'?s?|phd|ph\.?d\.?|doctoral)\s+(?:degree\s+)?(?:student|candidate)"
    r"|pursuing\s+(?:a\s+)?(?:master|phd|ph\.?d\.?|doctora))",
    re.I,
)

# Wording that puts an undergraduate back in scope. Checked FIRST, because the
# single most common phrasing in a real posting is "Bachelor's, Master's or PhD"
# — a list of acceptable degrees, not a graduate-only requirement, and reading
# it as the latter would discard most of the inbox.
_UNDERGRAD_OK = re.compile(
    r"\b(bachelor'?s?|undergraduate|b\.?s\.?|b\.?a\.?)\b", re.I
)


def requires_a_graduate_degree(requirements: list[str], posting_text: str) -> str | None:
    """The sentence demanding a graduate degree, or None.

    Returns the evidence rather than a boolean so a wrong call is visible and
    arguable instead of silently removing a job.

    Requirements are checked before the body here, the opposite of the
    graduation-year rule, and for a good reason: a degree requirement is a rule,
    and the requirements list is where rules live. The body mentions degrees in
    passing constantly ("our team holds advanced degrees"), which is not a
    requirement of you.

    Any mention of a bachelor's in the same sentence clears it. "Bachelor's,
    Master's or PhD in Computer Science" is a list of what they accept.
    """
    for source in [*requirements, *(_SENTENCE_SPLIT.split(posting_text or ""))]:
        if _UNDERGRAD_OK.search(source):
            continue
        if _GRADUATE_ONLY.search(source):
            return _excerpt(source)
    return None
