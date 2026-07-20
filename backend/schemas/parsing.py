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

    # Optional: absent in many postings, so they default to None / empty.
    deadline: date | None = None
    salary: str | None = None
    location: str | None = None
    summary: str | None = None
    # Pydantic copies this default per-instance, so the usual Python
    # mutable-default trap (every instance sharing one list) doesn't apply.
    key_requirements: list[str] = []

class ParseRequest(BaseModel):
    text: str

