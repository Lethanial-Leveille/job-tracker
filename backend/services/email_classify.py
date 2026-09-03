"""Email classification: one Gmail message in, three extracted facts out.

The fourth AI integration, and the cheapest. Parsing extracts from a posting,
tailoring writes a resume, requirement matching compares two documents; this one
reads two sentences. It runs on the cheap model (settings.anthropic_model,
Haiku) for the same reason the parser does.

HTTP-ignorant like every service: plain arguments in, an EmailClassification or
None out. Structured outputs, the same `client.messages.parse(output_format=...)`
pattern as services/parsing.py, so the reply is forced into the schema and
validated rather than hand-parsed.

WHAT THE MODEL SEES, AND WHY IT IS SO LITTLE
--------------------------------------------
Only the subject, the sender, and Gmail's `snippet` — roughly the first 200
characters of the message. The full body is never fetched. That was a deliberate
call, not a limitation worked around:

  - The snippet already carries all three facts for transactional mail. "Thank
    you for submitting your application for the Software Engineer Intern 2027
    position at Neighbor" is kind, organization, and role in one sentence.
  - Fetching bodies means base64url-decoding multipart MIME on the Raspberry Pi
    or shipping whole raw messages to the droplet. Neither is worth it.
  - Far less sensitive data crosses the network and none of it rests on the
    droplet (hard rule #5).
  - A snippet is CLEANER input, not merely smaller. A full body is mostly legal
    footer, unsubscribe links, and equal-opportunity boilerplate; the 200
    characters Gmail picks are the opening line, which for this kind of mail is
    the summary.

The known cost: a rejection that opens with a warm preamble ("Thank you for
taking the time to apply and for sharing your background...") can have its actual
verdict fall outside the window, making it look like a confirmation. The prompt
answers that by making "other" the cheap, expected answer rather than forcing a
guess — see rule 2 below.
"""

import logging

from anthropic import Anthropic

from config import Settings
from schemas.email import EmailClassification

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You read one email an applicant received about a job
application and extract three facts from it.

You are shown the SUBJECT, the SENDER, and a SNIPPET: roughly the first 200
characters of the message, not the whole thing. Assume text you cannot see.

`kind` is what the message is doing:
- "application_received": confirming an application was submitted or received.
- "rejection": declining the applicant, at any stage.
- "interview_invite": asking to schedule or attend an interview, screen, or
  assessment.
- "offer": extending an offer.
- "other": anything else, INCLUDING anything you cannot tell from what you were
  shown.

Rules:

1. Use only the subject, sender, and snippet. Do not infer what a message
   "probably" says beyond its visible text.

2. Prefer "other" whenever the snippet does not clearly settle the kind. This is
   the most important rule here. A rejection often opens with warm thanks and
   states the decision further down, outside the snippet you can see, so an
   opening that merely thanks the applicant for applying is NOT by itself a
   confirmation. A wrong kind creates a false suggestion for a human to catch; a
   wrong "other" creates no suggestion at all. The second mistake is much
   cheaper, so when torn, choose "other".

3. `organization` is the HIRING COMPANY named in the text, never the sender's
   domain. Applicant tracking systems (Lever, Greenhouse, iCIMS, Workday,
   Ashby, SmartRecruiters) send on behalf of hundreds of employers, so a
   sender of "no-reply@hire.lever.co" tells you nothing about who is hiring —
   but a display name of "Neighbor" or the company named in the body does. If
   the text names no employer, return null. Never return the vendor's name.

4. `role_hint` is the job title exactly as it appears, with no tidying,
   expansion, or normalizing. "Software Engineer Intern 2027" stays exactly
   that. If no title appears, return null.

5. Null is a good answer for `organization` and `role_hint`. Do not guess at
   either to avoid returning null."""


def classify_email(
    subject: str | None,
    from_name: str | None,
    from_email: str,
    snippet: str | None,
    settings: Settings,
) -> EmailClassification | None:
    """Extract kind, organization, and role hint from one message.

    Returns None when the model declines or the reply is cut off before a
    complete object (the SDK surfaces both as parsed_output=None). The caller
    treats None as "not classified", records nothing, and lets the next poll
    redeliver the message — so a None here costs a retry, never a lost email.
    Network and auth failures raise instead.

    An email with no subject and no snippet is answered as "other" WITHOUT
    spending an API call: there is nothing to read, and the answer is already
    known.
    """
    if not (subject or "").strip() and not (snippet or "").strip():
        return EmailClassification(kind="other")

    # The sender is given as its two parts rather than the raw header, because
    # splitting already happened upstream (email.utils.parseaddr in the ingest
    # service) and re-parsing here would put the same job in two places. The
    # display name matters as much as the address: for "Neighbor
    # <no-reply@hire.lever.co>" the employer is in the name and the vendor is in
    # the domain, which is exactly the distinction rule 3 asks the model to make.
    sender = f"{from_name} <{from_email}>" if from_name else from_email

    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"SUBJECT: {subject or '(none)'}\n"
                    f"SENDER: {sender}\n"
                    f"SNIPPET: {snippet or '(none)'}"
                ),
            }
        ],
        output_format=EmailClassification,
    )

    result = response.parsed_output
    if result is None:
        logger.warning("Email classification returned nothing for %r", subject)
    return result
