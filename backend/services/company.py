"""CRUD for the target company list.

Thin by design: the interesting rules live in schemas/company.py, where a
half-configured board is rejected before it can reach a nightly run.

The one thing worth doing carefully is the PATCH. A partial update cannot be
validated on its own — "set ats to workday" is fine in isolation and broken
against a row that only has a Greenhouse board token — so the merged result is
what gets checked.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.target_company import TargetCompany
from schemas.company import TargetCompanyCreate, TargetCompanyUpdate


def list_companies(db: Session, user_id: str) -> list[TargetCompany]:
    return list(
        db.execute(
            select(TargetCompany)
            .where(TargetCompany.user_id == user_id)
            .order_by(TargetCompany.name)
        ).scalars().all()
    )


def get_company(db: Session, company_id: str, user_id: str) -> TargetCompany | None:
    """Owner-scoped, so someone else's row is indistinguishable from a missing
    one and the route 404s rather than revealing it exists."""
    return db.execute(
        select(TargetCompany).where(
            TargetCompany.id == company_id, TargetCompany.user_id == user_id
        )
    ).scalar_one_or_none()


def create_company(
    db: Session, data: TargetCompanyCreate, user_id: str
) -> TargetCompany:
    # user_id comes from the authenticated user, never the body — a client
    # cannot choose who owns a row.
    company = TargetCompany(**data.model_dump(), user_id=user_id)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def update_company(
    db: Session, company: TargetCompany, data: TargetCompanyUpdate
) -> TargetCompany:
    """Apply a partial update, validating the RESULT rather than the patch.

    Changing the ATS alone is the case that makes this necessary: switching a
    row from Greenhouse to Workday is valid as an isolated field and leaves the
    row missing a hostname and a site id. Only the merged version can be judged.
    """
    changes = data.model_dump(exclude_unset=True)
    merged = {
        "name": company.name,
        "ats": company.ats,
        "board": company.board,
        "host": company.host,
        "site": company.site,
        "active": company.active,
        **changes,
    }
    # Raises ValidationError, which the route turns into a 422 the same way it
    # would for a bad create.
    TargetCompanyCreate(**merged)

    for field, value in changes.items():
        setattr(company, field, value)
    # A configuration change makes the previous failure meaningless — keeping it
    # would leave a fixed company looking broken until the next nightly run.
    if changes:
        company.last_error = None
    db.commit()
    db.refresh(company)
    return company


def delete_company(db: Session, company: TargetCompany) -> None:
    """Remove a company. Its discoveries survive.

    The foreign key is SET NULL rather than a cascade: jobs this company's board
    already found, some of which you may have accepted, should not vanish
    because you stopped watching the board.
    """
    db.delete(company)
    db.commit()
