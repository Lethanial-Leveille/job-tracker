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

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from schemas.fit import FitReport

from models.application import (
    ApplicationStatus,
    ApplicationType,
    DeadlineSource,
    Priority,
)
from schemas.roles import ROLE_FAMILIES, RoleFamily


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

    # Whether `deadline` above is the posting's date or one you set yourself.
    # Null means unknown, which is a real third answer here rather than a
    # missing value: rows predating this field have no evidence either way, and
    # a warning about a missed deadline must not fire on a guess.
    deadline_source: DeadlineSource | None = None

    notes: str | None = None

    # The tidy, groupable version of role_or_program, normally filled by the
    # parser (schemas/roles.py explains why). Optional and nullable: a row added
    # by hand may not have one, and the Literal means an unrecognized family is
    # a 422 rather than silently stored, even though the column is a VARCHAR.
    role_family: RoleFamily | None = None


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
    # Editable, because the two move together: changing a date by hand usually
    # means it is now yours rather than the posting's, and the caller is the
    # only one who knows which.
    deadline_source: DeadlineSource | None = None
    notes: str | None = None
    role_family: RoleFamily | None = None
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
    """One stored application, as the API returns it.

    Two fields here are validated against something narrower than their column,
    and both have taken the whole list down before. `fit_report` is a JSON blob
    parsed through FitReport; `role_family` is a Literal over a plain VARCHAR.
    Because the list response is `list[ApplicationRead]`, ONE row that fails
    either check 500s the entire pipeline — you do not lose a row, you lose the
    page, and nothing on screen says which row did it.

    So both degrade instead. A report that cannot be parsed reads as "not
    computed", and a family outside the vocabulary reads as "unset". Both are
    cosmetic losses on one row; a blank pipeline is not.

    This is the failure CLAUDE.md's stored-JSON rule is about, and adding a
    default to new fields prevents only half of it — the other half is old data
    that was valid when it was written and is not any more.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    jd_parsed: dict | None = None
    jd_text: str | None = None
    # The cached requirement-match report, or null if it has not been computed
    # for this application yet. Read-only: it is written by POST /{id}/fit, not
    # by create or update, so no human-typed schema carries it.
    fit_report: FitReport | None = None

    @field_validator("fit_report", mode="before")
    @classmethod
    def _tolerate_an_unreadable_report(cls, value: object) -> object:
        """Drop a report this schema can no longer read, rather than 500.

        A cached report is a convenience: it is recomputed on demand by
        POST /{id}/fit, and showing nothing prompts exactly that. Refusing to
        serve the application it belongs to is not a proportionate response to a
        stale cache.
        """
        if value is None or isinstance(value, FitReport):
            return value
        try:
            return FitReport.model_validate(value)
        except ValidationError:
            return None

    @field_validator("role_family", mode="before")
    @classmethod
    def _tolerate_an_unknown_family(cls, value: object) -> object:
        """Read a family outside the vocabulary as unset.

        The column is a VARCHAR and the Literal is the only thing enforcing the
        set, precisely so that adding a family is a code change rather than a
        migration. The cost of that choice is exactly this: retire or rename one
        and every row still holding the old string becomes unreadable. Losing
        the tidy label on a row is a fair price; losing the pipeline is not.
        """
        if value is None or value in ROLE_FAMILIES:
            return value
        return None

    @field_validator("deadline_source", mode="before")
    @classmethod
    def _tolerate_an_unknown_deadline_source(cls, value: object) -> object:
        """Read a source outside the vocabulary as unknown.

        Same trade as the family above, and the same reason: the column is a
        VARCHAR so that adding a source later is a code change rather than a
        migration. Degrading to None is safe in a way it would not be for most
        fields, because None already means "no evidence" here, and every
        consumer of this field is required to treat unknown as "do not warn".
        """
        if value is None:
            return None
        raw = value.value if isinstance(value, DeadlineSource) else str(value)
        return raw if raw in {m.value for m in DeadlineSource} else None
    # Derived, never stored: the first time this row reached `applied`, read out
    # of the status history by services/application.py. It exists so the list can
    # answer "how long have I been waiting" without a per-row timeline fetch.
    # Optional because a row that has never been applied to has no such event.
    applied_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
