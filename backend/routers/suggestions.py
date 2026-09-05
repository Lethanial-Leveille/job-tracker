"""Status-suggestion review routes: the logged-in user's side of the Gmail pipeline.

The webhook (routers/webhooks.py) stages suggestions as a machine; these routes
let the person list them and resolve them. Guarded by get_current_user like the
rest of the human-facing API — the opposite auth path from the webhook.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.suggestion import SuggestionAccept, SuggestionRead
from services.status_suggestion import (
    accept_suggestion,
    dismiss_suggestion,
    list_pending_suggestions,
)

router = APIRouter(
    prefix="/suggestions",
    tags=["suggestions"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[SuggestionRead])
def list_suggestions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SuggestionRead]:
    # Pending suggestions only, newest first, each with its triggering email.
    return [
        SuggestionRead.from_parts(s, email)
        for s, email in list_pending_suggestions(db, user.id)
    ]


@router.post("/{suggestion_id}/accept", response_model=SuggestionRead)
def accept(
    suggestion_id: str,
    data: SuggestionAccept,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SuggestionRead:
    # Applying a status is the one write an email can cause, and only here, by a
    # click. A bad/missing target choice is a 400; an unknown suggestion is a 404.
    try:
        suggestion = accept_suggestion(db, user.id, suggestion_id, data.application_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    return SuggestionRead.from_parts(suggestion)


@router.post("/{suggestion_id}/dismiss", response_model=SuggestionRead)
def dismiss(
    suggestion_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SuggestionRead:
    suggestion = dismiss_suggestion(db, user.id, suggestion_id)
    if suggestion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Suggestion not found"
        )
    return SuggestionRead.from_parts(suggestion)
