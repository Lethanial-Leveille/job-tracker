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

from pydantic import BaseModel


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
