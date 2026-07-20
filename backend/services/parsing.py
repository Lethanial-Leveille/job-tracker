"""The JD parsing service: raw posting text in, structured ParsedJob out.

This is the app's first AI integration. It stays HTTP-ignorant (same rule as the
CRUD services): it takes plain text plus settings and returns a ParsedJob or
None, so a route, an n8n webhook, or a test can all call it the same way.

The extraction uses structured outputs: we hand Claude the ParsedJob schema via
`output_format`, and the SDK forces the reply to match that shape and validates
it, returning a typed ParsedJob. No hand-parsing of JSON, no hoping the model
formatted it right.
"""

from anthropic import Anthropic

from config import Settings
from schemas.parsing import ParsedJob

# The prompt guides *content*; the schema (passed as output_format) constrains
# *shape*. The two "leave it null / don't invent" lines are the guardrail from
# vision.md applied at the parsing layer: tailoring can rephrase, but the parser
# must never fabricate a deadline, salary, or requirement the posting didn't state.
_SYSTEM_PROMPT = """You extract structured fields from a job or scholarship posting.

Rules:
- Use only information stated in the posting. Do not infer or invent anything.
- If a field is not stated, leave it null (or an empty list for requirements).
- Set `type` to "scholarship" for scholarships, awards, grants, and fellowships;
  otherwise "internship".
- `summary` is a one or two sentence plain description of the role or program.
- `key_requirements` are the stated eligibility or qualification bullet points."""


def parse_job_description(text: str, settings: Settings) -> ParsedJob | None:
    """Parse posting text into a ParsedJob, or None if Claude can't.

    Returns None when the model declines (safety refusal) or the reply is cut
    off before a complete object — the SDK surfaces both as parsed_output=None.
    Network or auth failures raise instead; the route decides how to present them.
    """
    client = Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.parse(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text}],
        output_format=ParsedJob,
    )
    return response.parsed_output
