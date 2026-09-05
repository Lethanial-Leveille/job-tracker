"""API shapes for reviewing status suggestions.

The read side of the Gmail pipeline: the webhook (routers/webhooks.py) STAGES
StatusSuggestion rows; these schemas are how the logged-in user lists and
resolves them. A suggestion carries a snapshot of the email that produced it so
the UI can show the evidence next to the proposed change.
"""

from datetime import datetime

from pydantic import BaseModel

from models.application import ApplicationStatus
from models.status_suggestion import SuggestionState


class SuggestionEmail(BaseModel):
    """The triggering email, shown as evidence beside the suggestion."""

    from_email: str
    from_name: str | None = None
    subject: str | None = None
    snippet: str | None = None
    received_at: datetime


class SuggestionRead(BaseModel):
    """One staged suggestion for the review UI.

    `application_id` set = resolved to one application (accept applies straight
    through). `candidate_application_ids` set (with a null application_id) = the
    UI must ask which one. Both null = nothing matched; the UI lets the user
    pick any application to apply it to, or dismiss it.
    """

    id: str
    suggested_status: ApplicationStatus
    reason: str
    application_id: str | None = None
    candidate_application_ids: list[str] | None = None
    state: SuggestionState
    created_at: datetime
    email: SuggestionEmail | None = None

    @classmethod
    def from_parts(
        cls, suggestion, email=None
    ) -> "SuggestionRead":
        """Build from a StatusSuggestion row and its (optional) IngestedEmail."""
        return cls(
            id=suggestion.id,
            suggested_status=suggestion.suggested_status,
            reason=suggestion.reason,
            application_id=suggestion.application_id,
            candidate_application_ids=suggestion.candidate_application_ids,
            state=suggestion.state,
            created_at=suggestion.created_at,
            email=(
                SuggestionEmail(
                    from_email=email.from_email,
                    from_name=email.from_name,
                    subject=email.subject,
                    snippet=email.snippet,
                    received_at=email.received_at,
                )
                if email is not None
                else None
            ),
        )


class SuggestionAccept(BaseModel):
    """Body for accepting a suggestion.

    Optional: needed only when the suggestion is unresolved (ambiguous, so the
    user picks one of the candidates; or unmatched, so the user picks any of
    their applications). A resolved suggestion ignores it — the target is fixed.
    """

    application_id: str | None = None
