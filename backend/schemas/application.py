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
# jd_parsed is deliberately absent: no parser exists in v1, so it is read-only
# (present in the response, never accepted in a request).


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
# Nothing extra to add: the POST body is exactly the base fields. Required stays
# required. id, timestamps, and jd_parsed are all server-managed and excluded.


class ApplicationCreate(ApplicationBase):
    pass


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
    created_at: datetime
    updated_at: datetime
