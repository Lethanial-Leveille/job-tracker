"""Tests for the target company watchlist.

Almost all of the value here is in rejecting a board that could never be read.
A company saved in a broken shape does not fail loudly — it sits in the list
returning nothing, once a night, forever, and the only symptom is an inbox
slightly thinner than it should be.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from models.user import User
from schemas.company import TargetCompanyCreate, TargetCompanyUpdate
from services.company import (
    create_company,
    delete_company,
    get_company,
    list_companies,
    update_company,
)


def _create(db: Session, user: User, **overrides: object):
    base = {"name": "Stripe", "ats": "greenhouse", "board": "stripe"}
    base.update(overrides)
    return create_company(db, TargetCompanyCreate(**base), user.id)  # type: ignore[arg-type]


# --- Validation --------------------------------------------------------------


@pytest.mark.parametrize(
    "config",
    [
        {"ats": "greenhouse"},
        {"ats": "lever"},
        {"ats": "ashby"},
        {"ats": "workday", "board": "acme"},
        {"ats": "workday", "host": "acme.wd5.myworkdayjobs.com", "board": "acme"},
        {"ats": "oracle", "host": "careers.acme.com"},
    ],
)
def test_an_incomplete_board_is_refused(config: dict) -> None:
    """Each system needs a different set of fields, and a missing one is silent.

    Three of the five identify a board with one string; Workday needs three and
    Oracle needs two. Saved incomplete, the request goes to a URL with a hole in
    it and 404s once a night.
    """
    with pytest.raises(ValidationError):
        TargetCompanyCreate(name="Acme", **config)  # type: ignore[arg-type]


def test_a_blank_identifier_counts_as_missing() -> None:
    # An empty string sails through a nullable column and produces a request to
    # ".../boards//jobs", which is a 404 that looks like a real answer.
    with pytest.raises(ValidationError):
        TargetCompanyCreate(name="Acme", ats="greenhouse", board="   ")


def test_the_error_names_the_field_you_have_to_fill() -> None:
    """"board is required" is useless when the box is called a tenant.

    The same column means a board token on Greenhouse, a company slug on Lever
    and a tenant on Workday, so the message has to speak the vendor's language.
    """
    with pytest.raises(ValidationError) as excinfo:
        TargetCompanyCreate(name="Acme", ats="workday", host="h", board="t")

    assert "site id" in excinfo.value.errors()[0]["msg"]


@pytest.mark.parametrize(
    "config",
    [
        {"ats": "greenhouse", "board": "stripe"},
        {"ats": "lever", "board": "matchgroup"},
        {"ats": "ashby", "board": "Sierra"},
        {"ats": "workday", "host": "adobe.wd5.myworkdayjobs.com", "board": "adobe", "site": "external"},
        {"ats": "oracle", "host": "careers.dell.com", "site": "CX_1001"},
    ],
)
def test_a_complete_board_is_accepted(config: dict) -> None:
    assert TargetCompanyCreate(name="Acme", **config) is not None  # type: ignore[arg-type]


# --- Updating ----------------------------------------------------------------


def test_a_patch_is_validated_against_the_merged_row(db: Session, user: User) -> None:
    """Changing the system alone is valid in isolation and breaks the row.

    Switching from Greenhouse to Workday leaves it with a board token and no
    hostname or site. Only the merged version can be judged, which is why the
    update schema does not carry the validator itself.
    """
    company = _create(db, user)

    with pytest.raises(ValidationError):
        update_company(db, company, TargetCompanyUpdate(ats="workday"))


def test_a_valid_patch_applies(db: Session, user: User) -> None:
    company = _create(db, user)

    updated = update_company(db, company, TargetCompanyUpdate(active=False))

    assert updated.active is False
    assert updated.board == "stripe"


def test_fixing_a_company_clears_its_last_error(db: Session, user: User) -> None:
    # Otherwise a company you just corrected keeps showing as broken until the
    # next nightly run, which reads as "the fix did not work".
    company = _create(db, user)
    company.last_error = "HTTPStatusError: 404"
    db.commit()

    updated = update_company(db, company, TargetCompanyUpdate(board="stripe-eng"))

    assert updated.last_error is None


# --- Ownership and deletion --------------------------------------------------


def test_another_users_company_is_invisible(db: Session, user: User) -> None:
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    theirs = _create(db, other, name="Theirs")

    assert list_companies(db, user.id) == []
    # None, not a permission error: the route 404s and never confirms it exists.
    assert get_company(db, theirs.id, user.id) is None


def test_removing_a_company_keeps_the_jobs_it_found(db: Session, user: User) -> None:
    """You may have accepted some of them.

    The foreign key is SET NULL rather than a cascade, so discoveries survive
    with their source name intact when you stop watching a board.
    """
    from sqlalchemy import select

    from models.discovered_job import DiscoveredJob

    company = _create(db, user)
    db.add(
        DiscoveredJob(
            user_id=user.id,
            source="greenhouse",
            target_company_id=company.id,
            external_id="1",
            organization="Stripe",
            role_or_program="Intern",
            posting_url="https://x/1",
        )
    )
    db.commit()

    delete_company(db, company)

    rows = list(db.execute(select(DiscoveredJob)).scalars().all())
    assert len(rows) == 1
    assert rows[0].target_company_id is None
    assert rows[0].source == "greenhouse"
