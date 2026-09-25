"""Automation endpoints: the HTTP surface n8n calls.

Separate router from the rest of the API because it uses the OTHER auth path.
Every other route is protected by get_current_user and belongs to a logged-in
person; these are protected by verify_service_token and belong to a machine.
Keeping them in their own module means the two can never be confused, and the
router-level dependency guards every route here by default so a new one cannot
be added unprotected by accident.

Two endpoints, both called by n8n on the Raspberry Pi on a schedule. Gmail
ingestion POSTs a rolling two day window of messages (see
services/email_ingest.py for why there is no cursor and why that is safe), and
the discovery pull runs the internship feed overnight so the inbox is filled in
by morning.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import verify_service_token
from models.user import User
from schemas.discovery import DiscoveryRunRead
from schemas.email import (
    EmailIngestRequest,
    EmailIngestResponse,
    MessageResult,
)
from services.discovery import RunAlreadyGoing, execute_run, start_run
from services.email_ingest import ingest_messages
from services.user import OwnerNotConfigured, get_owner

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

logger = logging.getLogger(__name__)


def _owner(db: Session, settings: Settings) -> User:
    """Whose rows these writes belong to, from config rather than the request.

    This used to come out of the request body: the Gmail webhook named a
    mailbox, the discovery webhook named an email, and each was looked up. That
    made sense while this was heading toward several people. It is now one
    person plus a dormant account, so asking the caller to name the owner is
    one more thing to keep in sync in an n8n node and one more way to get a
    confusing 404 at three in the morning.

    n8n may keep sending those fields. Pydantic ignores what a model does not
    declare, so nothing on the Pi has to change at the same time as this.
    """
    try:
        return get_owner(db, settings)
    except OwnerNotConfigured as exc:
        logger.error("A webhook call could not resolve an owner: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The owner is not configured on this server.",
        ) from exc


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

    The one real error is the 500 from _owner: the server has no OWNER_EMAIL
    set. That is a configuration mistake on the droplet rather than a transient
    failure, so it fails loudly and keeps failing until someone fixes it.
    """
    owner = _owner(db, settings)
    outcomes = ingest_messages(db, owner.id, data.messages, settings)

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


@router.post(
    "/discovery/pull",
    response_model=DiscoveryRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def pull_discoveries(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> DiscoveryRunRead:
    """Start the nightly discovery pull for one user and answer immediately.

    202 rather than 200, and it is Cloudflare that forces it. The site sits
    behind a tunnel, and Cloudflare abandons any request the origin has not
    answered within 100 seconds, returning a 524 to the caller. A pull downloads
    a 12MB feed, classifies every new title, and then fetches and reads up to
    fifty postings one at a time — well past that. Held open, this endpoint
    would hand n8n a failure for a run that was working fine, and n8n would
    retry it, and the retry would collide with the run still going.

    So the request validates, claims a run, hands the work to a background task,
    and returns the run row. Poll nothing from n8n: the row is the record, and
    the Discovered page reads it.

    Three answers worth knowing about:
      202 — accepted, the run is going. The body carries its id.
      409 — one is already in progress. Not an error to alert on; it means the
            schedule fired twice or a manual pull is running.
      500 — the server has no owner configured. A misconfigured droplet rather
            than a transient failure, so it fails loudly and keeps failing.
    """
    owner = _owner(db, settings)

    try:
        run = start_run(db, owner.id)
    except RunAlreadyGoing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pull is already running for that user.",
        ) from exc

    background.add_task(execute_run, run.id, owner.id, settings)
    return DiscoveryRunRead.model_validate(run)
