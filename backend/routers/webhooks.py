"""Automation endpoints: the HTTP surface n8n calls.

Separate router from the rest of the API because it uses the OTHER auth path.
Every other route is protected by get_current_user and belongs to a logged-in
person; these are protected by verify_service_token and belong to a machine.
Keeping them in their own module means the two can never be confused, and the
router-level dependency guards every route here by default so a new one cannot
be added unprotected by accident.

Currently one endpoint: Gmail ingestion. n8n on the Raspberry Pi polls Gmail on
a schedule and POSTs a rolling two day window of messages here. See
services/email_ingest.py for why there is no cursor and why that is safe.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import verify_service_token
from schemas.email import (
    EmailIngestRequest,
    EmailIngestResponse,
    MessageResult,
)
from services.email_ingest import ingest_messages
from services.user import get_user_by_email

# dependencies=[Depends(verify_service_token)] guards EVERY route here, so a
# route added later is protected without anyone remembering to protect it. Same
# fail-safe pattern the applications router uses with get_current_user.
router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
    dependencies=[Depends(verify_service_token)],
)

# Results that mean a new row was written to ingested_emails.
_STORED_RESULTS = frozenset({"suggested", "ambiguous", "unmatched", "no_action"})
_SUGGESTION_RESULTS = frozenset({"suggested", "ambiguous", "unmatched"})


@router.post("/email", response_model=EmailIngestResponse)
def ingest_email(
    data: EmailIngestRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EmailIngestResponse:
    """Take a batch of Gmail messages and stage any status suggestions they imply.

    Nothing here writes to an application's status. Each message becomes at most
    one StatusSuggestion for a human to accept — see services/email_ingest.py.

    Answers 200 whenever the batch was handled, even if individual messages
    failed to classify. A per-message failure is not a failed request: those
    messages simply went unrecorded, and the rolling window redelivers them on
    the next poll. Returning an error would make n8n retry the whole batch and
    re-bill every message that already succeeded.

    The 404 below is the one real error. It means the mailbox n8n is polling has
    no matching user, which is a configuration mistake on the Pi rather than a
    transient failure, so it is worth failing loudly and repeatedly until fixed.
    """
    user = get_user_by_email(db, data.mailbox)
    if user is None:
        # No hint about which mailboxes DO exist. The caller holds the service
        # token, but this stays terse out of habit rather than necessity.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No user for that mailbox",
        )

    outcomes = ingest_messages(db, user.id, data.messages, settings)

    return EmailIngestResponse(
        received=len(outcomes),
        stored=sum(1 for o in outcomes if o.result in _STORED_RESULTS),
        suggestions_created=sum(
            1 for o in outcomes if o.result in _SUGGESTION_RESULTS
        ),
        retry=sum(1 for o in outcomes if o.result == "not_classified"),
        results=[
            MessageResult(message_id=o.message_id, result=o.result)
            for o in outcomes
        ],
    )
