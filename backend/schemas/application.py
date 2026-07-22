"""Pydantic schemas for the Application resource.

Schemas are the API's contract. Each one declares exactly which fields a request
may send or a response will return, and validates incoming JSON against that
shape. One schema per operation, sharing a common base:

    ApplicationBase   — human-supplied fields, shared by create and update
    ApplicationCreate — the POST body (required fields required)
    ApplicationUpdate — the PATCH body (every field optional, for partial edits)
    ApplicationRead   — the response body (adds server-managed fields)

The enums are imported from the model, not re-declared here, so request
validation and database storage can never drift apart.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.application import (
    ApplicationStatus,
    ApplicationType,
    Priority,
)


# --- Shared base -------------------------------------------------------------
# The fields a person actually types. Create and Update both build on this set,
# so field definitions (max lengths, descriptions) live in exactly one place.
# jd_parsed is not here because it isn't a human-typed field: Create adds it (to
# carry v2 parser extras), Update omits it, Read returns it. See each below.


class ApplicationBase(BaseModel):
    type: ApplicationType
    organization: str = Field(min_length=1, max_length=255)
    role_or_program: str = Field(min_length=1, max_length=255)
    posting_url: str = Field(min_length=1, max_length=2048)

    # Optional-with-default. The client MAY set these on create; if omitted, the
    # database defaults (discovered / medium) apply. Matches how you'll actually
    # use it — adding a row you've already applied to, or flagging priority up
    # front.
    status: ApplicationStatus = ApplicationStatus.discovered
    priority: Priority = Priority.medium

    # Genuinely optional, no default value.
    deadline: date | None = None
    notes: str | None = None


# --- Create ------------------------------------------------------------------
# The base fields, plus jd_parsed. As of v2 the parser returns extras (salary,
# summary, requirements) with no column of their own, so create accepts a
# jd_parsed blob to carry them into storage. Optional: a manual create omits it
# (defaults to None); an autofilled create sends the parser's extras. id and
# timestamps stay server-managed and excluded.


class ApplicationCreate(ApplicationBase):
    jd_parsed: dict | None = None
    # The raw JD text, carried in from the autofill paste so tailoring can later
    # run against the real posting. Optional: a manual create omits it.
    jd_text: str | None = None


# --- Update ------------------------------------------------------------------
# A PATCH should let you change just one field, so EVERY field is optional here.
# This class does not inherit from ApplicationBase on purpose: the base makes
# type/organization/etc required, which would defeat partial updates. A None
# value means "field omitted, leave it as is" — the route/service layer only
# applies fields the client actually sent.


class ApplicationUpdate(BaseModel):
    type: ApplicationType | None = None
    organization: str | None = Field(default=None, min_length=1, max_length=255)
    role_or_program: str | None = Field(
        default=None, min_length=1, max_length=255
    )
    posting_url: str | None = Field(default=None, min_length=1, max_length=2048)
    status: ApplicationStatus | None = None
    priority: Priority | None = None
    deadline: date | None = None
    notes: str | None = None
    # Re-settable input (unlike jd_parsed, which update omits): lets you paste a
    # JD onto an application created by hand so the tailoring button can use it.
    jd_text: str | None = None


# --- Read --------------------------------------------------------------------
# The response body. Everything the base has, plus the server-managed fields the
# client never sets. jd_parsed shows up here (read-only) so the response shape
# is already stable when v2's parser starts filling it.
#
# from_attributes=True lets FastAPI build this straight from a SQLAlchemy row
# object (reading .id, .organization, etc. as attributes) instead of requiring
# a plain dict.


class ApplicationRead(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    jd_parsed: dict | None = None
    jd_text: str | None = None
    created_at: datetime
    updated_at: datetime
