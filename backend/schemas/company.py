"""Shapes for the target company list: the employers whose boards we poll.

The validation here is the point of the module. Three of the five systems
identify a board with one string and two need three, so a company can be saved
in a shape that looks fine and silently returns nothing every night. Catching
that at the API boundary means it fails while you are typing it rather than at
3am into a log nobody reads.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from models.target_company import ATS_NAMES

Ats = Literal["greenhouse", "lever", "ashby", "workday", "oracle"]

# Which identifier columns each system actually needs. Derived into the error
# message below, so adding a system means editing one table rather than three.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "greenhouse": ("board",),
    "lever": ("board",),
    "ashby": ("board",),
    "workday": ("host", "board", "site"),
    "oracle": ("host", "site"),
}

# What to call each field when telling someone what is missing. "board" means
# something different on every system, and "board is required" is useless when
# the box you need to fill is called a tenant.
_LABELS: dict[tuple[str, str], str] = {
    ("greenhouse", "board"): "board token (the name in the boards.greenhouse.io URL)",
    ("lever", "board"): "company slug (the name in the jobs.lever.co URL)",
    ("ashby", "board"): "organization name (the name in the jobs.ashbyhq.com URL)",
    ("workday", "host"): "hostname, e.g. acme.wd5.myworkdayjobs.com",
    ("workday", "board"): "tenant, the first part of the hostname",
    ("workday", "site"): "site id, e.g. external_experienced",
    ("oracle", "host"): "hostname, e.g. careers.acme.com",
    ("oracle", "site"): "site number, e.g. CX_1001",
}


class TargetCompanyBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    ats: Ats
    board: str | None = Field(default=None, max_length=255)
    host: str | None = Field(default=None, max_length=255)
    site: str | None = Field(default=None, max_length=255)
    active: bool = True

    @model_validator(mode="after")
    def _identifier_is_complete(self) -> "TargetCompanyBase":
        """Every field this system needs must be present and non-blank.

        Blank counts as missing. An empty string sails through a nullable
        column and produces a request to `.../boards//jobs`, which 404s once a
        night forever.
        """
        missing = [
            field
            for field in _REQUIRED[self.ats]
            if not (getattr(self, field) or "").strip()
        ]
        if missing:
            named = ", ".join(
                _LABELS.get((self.ats, field), field) for field in missing
            )
            raise ValueError(f"{self.ats} needs a {named}")
        return self


class TargetCompanyCreate(TargetCompanyBase):
    pass


class TargetCompanyUpdate(BaseModel):
    """A PATCH, so every field is optional.

    Deliberately NOT inheriting from the base: that would make the identifier
    fields required again and defeat partial updates, and its validator cannot
    run on a body that carries one field. The service re-validates the merged
    result instead, which is the only version that can be checked honestly.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    ats: Ats | None = None
    board: str | None = None
    host: str | None = None
    site: str | None = None
    active: bool | None = None


class TargetCompanyRead(TargetCompanyBase):
    id: str
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# Exported so the UI can build its form from the same table the validator uses,
# rather than from a second copy that drifts.
ATS_REQUIREMENTS: dict[str, list[str]] = {
    ats: list(fields) for ats, fields in _REQUIRED.items()
}
assert set(ATS_REQUIREMENTS) == set(ATS_NAMES)


class IdentifyRequest(BaseModel):
    url: str = Field(min_length=1)


class IdentifyResult(BaseModel):
    """What a careers link turns out to be, and whether it is worth adding.

    `internships` is the part that earns this its network call. A watchlist
    entry that parses correctly and returns nothing is indistinguishable from a
    company with no openings, and you would not find out for weeks. Reading the
    board once, at the moment you are adding it, turns that into a number you
    can see before you commit.

    Zero is not necessarily wrong — plenty of companies have no internships open
    in a given month — which is why this reports rather than refuses.
    """

    ats: Ats
    board: str | None = None
    host: str | None = None
    site: str | None = None
    # How many internships that board is advertising right now.
    internships: int = 0
    # A couple of titles, so "7 internships" is checkable rather than trusted.
    sample: list[str] = []
