"""The shape of what Claude returns when it parses a posting.

This is the AI's *output* schema, deliberately separate from the application
schemas. It is content, not storage: the required fields map onto real DB
columns later, and the optional extras get bundled into the jd_parsed JSON blob
during mapping. Nothing here knows about the database — it only describes what a
good extraction looks like.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from schemas.roles import RoleFamily


class ParsedJob(BaseModel):
    """Fields Claude extracts from a job or scholarship posting.

    Required fields (no default) must always come back — a posting Claude can't
    identify an organization or role for is a failed parse. Optional fields
    default to "not stated" so a posting that simply omits salary or a deadline
    parses cleanly instead of failing validation.
    """

    # Required: Claude infers which kind of posting this is from the text.
    type: Literal["internship", "scholarship"]
    organization: str
    role_or_program: str
    # The posted title normalized to one of a fixed set (schemas/roles.py). This
    # is the one field Claude CLASSIFIES rather than extracts: the posting never
    # states its role family, so the no-inference rule below cannot apply to it.
    # role_or_program still holds the title exactly as posted.
    role_family: RoleFamily

    # Optional: absent in many postings, so they default to None / empty.
    deadline: date | None = None
    salary: str | None = None
    location: str | None = None
    summary: str | None = None
    # Pydantic copies this default per-instance, so the usual Python
    # mutable-default trap (every instance sharing one list) doesn't apply.
    #
    # HARD requirements only — the "You have" / "Required" / "Minimum
    # qualifications" list. What gates you.
    key_requirements: list[str] = []

    # The "We prefer" / "Nice to have" / "Preferred qualifications" list, kept
    # SEPARATE rather than folded into key_requirements.
    #
    # Merging them would be the obvious move and it is wrong twice: it turns
    # "3 of 4 required met" into "3 of 9", which reads as a weak fit for someone
    # who clears every hard requirement, and it makes a missing preference look
    # identical to a missing requirement. Kept apart, the preferred list becomes
    # the useful half — nearly every applicant clears the hard bar, so this is
    # where candidates actually separate, and it is a concrete list of what to
    # surface when tailoring.
    preferred_qualifications: list[str] = []

class ParseRequest(BaseModel):
    text: str

