"""How well the user's master resume answers a posting's stated requirements.

Deliberately NOT a probability of getting the job. That number would need an
outcome history the app does not have, and a model asked for it would return
something that looks authoritative and means nothing. What IS answerable from
data on hand: the posting states its requirements (the parser already extracts
them into jd_parsed.key_requirements), the master resume states what you have
done, and those two can be compared item by item with the evidence shown.

So the output is diagnostic, not predictive: which requirements you meet, which
you partly meet, which you do not, and what in your own resume supports each
call. That tells you what to shore up. A percentage would not.

Two schemas, on purpose:

    _RequirementVerdict — what CLAUDE returns, one verdict per requirement
    FitReport           — what we STORE and return, counts computed in Python
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel

# What the model is allowed to answer. "partial" is the honest middle: adjacent
# experience that a recruiter might or might not accept.
ModelVerdict = Literal["met", "partial", "missing"]

# What a stored report may contain. "unknown" is never produced by the model —
# Python assigns it to any requirement the model failed to answer for, so the
# denominator stays honest instead of a dropped item silently reading as met.
StoredVerdict = Literal["met", "partial", "missing", "unknown"]


class RequirementVerdict(BaseModel):
    """One requirement, judged. `index` ties the answer back to its input.

    Same reason as _ClassifiedRole in services/parsing.py: requirements in a
    posting are long and often near-identical to each other ("experience with
    Python", "experience with Python or Java"), so matching answers back by
    string would silently mis-assign one. An integer cannot be paraphrased.
    """

    index: int
    verdict: ModelVerdict
    # What in the master resume supports the verdict. Null for "missing" — there
    # is nothing to cite.
    evidence: str | None = None


class RequirementVerdicts(BaseModel):
    verdicts: list[RequirementVerdict]


class RequirementMatch(BaseModel):
    """One requirement paired back with its verdict, ready to display."""

    requirement: str
    verdict: StoredVerdict
    evidence: str | None = None


class FitReport(BaseModel):
    """The stored, displayable report.

    The counts are computed in Python from `matches`, never asked of the model.
    A language model asked to both list nine verdicts and total them will
    occasionally return a total that disagrees with its own list, and the number
    is the part someone reads at a glance.
    """

    matches: list[RequirementMatch]
    met_count: int
    partial_count: int
    total: int
    computed_at: datetime

    @classmethod
    def from_matches(cls, matches: list[RequirementMatch]) -> "FitReport":
        return cls(
            matches=matches,
            met_count=sum(1 for m in matches if m.verdict == "met"),
            partial_count=sum(1 for m in matches if m.verdict == "partial"),
            total=len(matches),
            computed_at=datetime.now(UTC),
        )
