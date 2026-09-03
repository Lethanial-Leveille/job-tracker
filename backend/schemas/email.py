"""What Claude extracts from one application-related email.

The AI's *output* schema, deliberately separate from the storage models — same
split as schemas/parsing.py. Nothing here knows about the database or about
applications; it only describes what can be read off a single message.

The scope is narrow on purpose. This schema extracts FACTS and nothing else: no
score, no recommendation, no guess about which application row the email
belongs to. Matching an email to a row is a decision, and decisions live in
services/email_ingest.py as ordinary Python that can be unit tested. The same
division as counting the fit report in code rather than asking the model to
total its own list.

Note there is no confidence field, and that is deliberate rather than an
oversight. A language model's self-reported confidence is not calibrated: it
will report high confidence about something it invented. A number that looks
like precision but is not would flow straight into the matching rule, which is
the one place in this pipeline that has to be deterministic. Ambiguity is
determined downstream, by counting how many applications survive narrowing.
"""

from typing import Literal

from pydantic import BaseModel, Field


class IncomingEmail(BaseModel):
    """One Gmail message as n8n forwards it, before any interpretation.

    Shaped by what the Gmail node actually returns with Simplify on, and kept
    deliberately raw. Two fields arrive unprocessed on purpose, because the work
    belongs on the droplet where it is testable rather than in an n8n Function
    node:

    - `from_raw` is the whole From header ("Neighbor <no-reply@hire.lever.co>").
      Python's email.utils.parseaddr handles the quoting and escaping cases in
      RFC 5322 that a hand-written regex gets wrong, e.g. '"Smith, Jane" <j@x>'.
    - `internal_date_ms` is Gmail's `internalDate`, epoch milliseconds. An
      integer is unambiguous over the wire; an ISO string invites timezone and
      format disagreements for no benefit.

    There is no body field. The Gmail node returns only `snippet` (~200
    characters) and that is all this pipeline ever sees — see
    services/email_classify.py for why that is a choice rather than a shortfall.
    """

    message_id: str
    thread_id: str | None = None
    internal_date_ms: int
    from_raw: str
    subject: str | None = None
    snippet: str | None = None

# What kind of message this is, from the applicant's point of view.
#
# "other" is not a failure bucket, it is the SAFE ANSWER, and the prompt leans on
# it hard. The classifier sees only Gmail's ~200 character snippet, and a
# rejection that opens with a warm preamble can look exactly like a confirmation
# within that window. A wrong `kind` produces a bad suggestion; "other" produces
# no suggestion at all, which lands back on the manual baseline. Given that, the
# cheaper mistake is obvious.
EmailKind = Literal[
    "application_received",
    "rejection",
    "interview_invite",
    "offer",
    "other",
]


class EmailClassification(BaseModel):
    """One email, reduced to the three facts the matching layer needs.

    This is stored whole in `ingested_emails.classification`, so per the
    stored-JSON rule in CLAUDE.md, any field ADDED here later needs a default:
    rows written today are read back through tomorrow's schema forever. The
    three below are present from the first row onward, so `kind` can stay
    required — which also keeps it required in the structured-output schema,
    where making it optional would invite the model to omit it.
    """

    kind: EmailKind

    # The HIRING COMPANY as named in the message, not the sender's domain.
    # Lever, Greenhouse, iCIMS and Workday send on behalf of hundreds of
    # employers, so `no-reply@hire.lever.co` says nothing about who is hiring.
    # Null when the text does not name one.
    organization: str | None = None

    # The job title as written, unmodified. Normalizing is the matching layer's
    # job (it has to agree with how applications were stored), so tidying here
    # would just make two places responsible for the same thing.
    role_hint: str | None = None


# --- The webhook contract ----------------------------------------------------
# What n8n on the Raspberry Pi POSTs, and what it gets back. This is the seam
# between two machines, so it is written to be boring: no nesting beyond one
# list, no fields that need interpreting, and a response n8n can log verbatim.


class EmailIngestRequest(BaseModel):
    """A batch of messages from one mailbox.

    `mailbox` is how the request names its owner. The service token
    authenticates the MACHINE — n8n has no user and verify_service_token
    deliberately returns nobody — so the mailbox address is what decides whose
    applications these messages may touch. Each n8n Gmail node reads exactly one
    mailbox, so it already knows this without being told.

    Worth being clear-eyed about: anyone holding the service token could claim
    any mailbox. The token IS the trust boundary, on infrastructure owned end to
    end, and that is an accepted trade rather than an oversight.
    """

    mailbox: str = Field(min_length=3, max_length=320)

    # Capped at 10. Classification is a model call per message and the endpoint
    # answers synchronously, so an unbounded batch could outlast n8n's HTTP
    # timeout, get retried mid-flight, and pay for the same work twice. Ten
    # keeps a batch well inside the timeout, and nothing is lost by splitting:
    # the rolling two day window redelivers whatever did not fit.
    messages: list[IncomingEmail] = Field(min_length=1, max_length=10)


class MessageResult(BaseModel):
    """What happened to one message, echoed back for n8n's logs."""

    message_id: str
    result: str


class EmailIngestResponse(BaseModel):
    """A summary n8n can log without interpreting.

    Deliberately returns 200 even when individual messages fail. A per-message
    failure is not a failed REQUEST: the batch was received and handled, and
    anything that failed is already scheduled for redelivery by the overlap
    window. Answering non-200 would make n8n retry the whole batch, re-billing
    every message that already succeeded.
    """

    received: int
    stored: int  # newly recorded this call
    suggestions_created: int
    retry: int  # not classified; the next poll will bring them back
    results: list[MessageResult]
