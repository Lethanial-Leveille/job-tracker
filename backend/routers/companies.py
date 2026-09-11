"""Target company routes: the watchlist behind the direct board polling.

Plain CRUD. The validation that matters happens in schemas/company.py, which
rejects a board that could never be read before it can sit in the list failing
silently every night.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.company import (
    ATS_REQUIREMENTS,
    IdentifyRequest,
    IdentifyResult,
    TargetCompanyCreate,
    TargetCompanyRead,
    TargetCompanyUpdate,
)
from services.boards import identify, read_board
from services.company import (
    create_company,
    delete_company,
    get_company,
    list_companies,
    update_company,
)

router = APIRouter(
    prefix="/companies",
    tags=["companies"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[TargetCompanyRead])
def read_all(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[TargetCompanyRead]:
    return [TargetCompanyRead.model_validate(c) for c in list_companies(db, user.id)]


@router.get("/requirements", response_model=dict[str, list[str]])
def read_requirements() -> dict[str, list[str]]:
    """Which identifier fields each system needs.

    Served rather than duplicated in the frontend so the form and the validator
    cannot drift: a sixth system, or a change to what Workday needs, updates
    both at once.
    """
    return ATS_REQUIREMENTS


@router.post("/identify", response_model=IdentifyResult)
def identify_board(data: IdentifyRequest) -> IdentifyResult:
    """Turn a careers link into a watchlist entry, and check that it works.

    Adding a company otherwise means knowing that Stripe's Greenhouse token is
    "stripe" and that Adobe's Workday site is "external_experienced" — real
    things you would have to go and find, per company, where getting one wrong
    produces an entry that returns nothing every night without saying why.

    This also READS the board, which is a slow thing to do in a request and
    worth it exactly once. An entry that parses correctly and finds nothing
    looks identical to a company with no openings, and you would not notice for
    weeks. Here it is a number on screen before you commit.

    404 when the link is not one of the five systems. That is a normal answer,
    not a failure: plenty of employers run their own careers site, and those
    cannot be polled directly at all.
    """
    found = identify(data.url)
    if found is None or not found.get("ats"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That is not a Greenhouse, Lever, Ashby, Workday or Oracle board. "
                "Companies on their own careers site can only come from the feed."
            ),
        )

    ats = str(found["ats"])
    missing = [field for field in ATS_REQUIREMENTS[ats] if not found.get(field)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"That looks like {ats}, but the link is missing the "
                f"{', '.join(missing)}. Try the board's front page rather than "
                "a single posting."
            ),
        )

    postings = read_board(ats, found.get("host"), found.get("board"), found.get("site"))
    return IdentifyResult(
        ats=ats,  # type: ignore[arg-type]
        board=found.get("board"),
        host=found.get("host"),
        site=found.get("site"),
        internships=len(postings),
        sample=[posting.title for posting in postings[:3]],
    )


@router.post("", response_model=TargetCompanyRead, status_code=status.HTTP_201_CREATED)
def create(
    data: TargetCompanyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TargetCompanyRead:
    return TargetCompanyRead.model_validate(create_company(db, data, user.id))


@router.patch("/{company_id}", response_model=TargetCompanyRead)
def update(
    company_id: str,
    data: TargetCompanyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TargetCompanyRead:
    company = _owned(db, company_id, user)
    try:
        return TargetCompanyRead.model_validate(update_company(db, company, data))
    except ValidationError as exc:
        # The merged row is invalid — e.g. switching to Workday without adding a
        # hostname. Reported as a 422 with the same message a bad create gives,
        # rather than as a 500.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors()[0]["msg"],
        ) from exc


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove(
    company_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    delete_company(db, _owned(db, company_id, user))


def _owned(db: Session, company_id: str, user: User):
    company = get_company(db, company_id, user.id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Company not found"
        )
    return company
