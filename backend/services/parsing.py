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
from pydantic import BaseModel

from schemas.parsing import ParsedJob
from schemas.roles import ROLE_FAMILIES, RoleFamily

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
- `key_requirements` are the stated eligibility or qualification bullet points.
- `role_or_program` is the title EXACTLY as posted, including any team or suffix
  ("Software Engineer Intern / Basketball Operations", "Software Engineer, Internship").
  It is REQUIRED and cannot be null, so the "leave it null" rule above does not
  apply to it. Never answer with a placeholder like "not stated", "unknown", or
  "N/A" — those become the row's title in the list and are worse than a rough
  guess. If the text carries no distinct job title (an application form, a
  program landing page), use the program or page heading instead, for example
  "Intern Program - Engineering Pathways".
- `role_family` is the one field you CLASSIFY rather than extract. Choose the
  single closest value from the allowed set. This is not inference about the
  posting's contents, so it is exempt from the no-inference rule above: every
  posting gets a family. Most engineering internships are "Software Engineer
  Intern" — use the specific families only when the posting is genuinely about
  that specialty, and "Other" when none of them honestly fit."""


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


# --- Backfill classification -------------------------------------------------
# role_family arrived after rows already existed, so those rows need classifying
# from their stored title alone (no posting text — the JD is not kept for rows
# added by hand). Separate from parse_job_description because the input is a
# title, not a posting, and the output is one field, not an extraction.


class _ClassifiedRole(BaseModel):
    """One title mapped to one family. `index` ties the answer back to its input.

    The model is asked to echo the index rather than the title: titles here are
    long and near-identical to each other, so matching answers back by string
    would silently mis-assign one. An integer cannot be paraphrased.
    """

    index: int
    role_family: RoleFamily


class _ClassifiedRoles(BaseModel):
    roles: list[_ClassifiedRole]


_CLASSIFY_PROMPT = f"""You classify job titles into a fixed set of role families.

You are given a numbered list of job titles. For each one, return its index and
the single closest role family from this exact set:

{chr(10).join("- " + r for r in ROLE_FAMILIES)}

Rules:
- Return one entry per input title, with the SAME index you were given.
- Most engineering internships are "Software Engineer Intern". Use a specific
  family only when the title is genuinely about that specialty.
- Use "Other" when none of them honestly fit. Do not force a bad match.
- Ignore season, year, location, and team suffixes: "Software Engineer Intern /
  Basketball Operations" and "Summer 2027 Intern - Software Engineer" are both
  plain "Software Engineer Intern"."""


def classify_role_families(
    titles: list[str], settings: Settings, max_rounds: int = 3
) -> dict[int, str] | None:
    """Map each title's position to a role family, or None if Claude can't.

    Returns a dict keyed by the title's index in `titles`. Any index still
    missing after `max_rounds` is simply absent, so the caller leaves that row
    alone rather than guessing — an unclassified row beats a wrong one.

    Why the retry loop: the model sometimes answers for only part of the list and
    stops cleanly (stop_reason "end_turn", well inside max_tokens), so this is
    not truncation and a bigger token budget does not fix it. Observed live: 16
    titles in, 8 answers back, indices 0-7. Each round re-asks ONLY for the
    titles still missing, using their ORIGINAL indices, so answers always map
    straight back and a partial reply costs one cheap extra call instead of a
    half-filled table.
    """
    if not titles:
        return {}

    client = Anthropic(api_key=settings.anthropic_api_key)
    resolved: dict[int, str] = {}

    for round_number in range(max_rounds):
        missing = [i for i in range(len(titles)) if i not in resolved]
        if not missing:
            break

        # Number by the ORIGINAL index, not by position in this round's subset,
        # so a second-round answer needs no re-mapping to be applied.
        numbered = "\n".join(f"{i}. {titles[i]}" for i in missing)
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=_CLASSIFY_PROMPT,
            messages=[{"role": "user", "content": numbered}],
            output_format=_ClassifiedRoles,
        )
        result = response.parsed_output
        if result is None:
            # A refusal on the first round means nothing to report; on a later
            # round, keep what earlier rounds already resolved.
            if round_number == 0:
                return None
            break

        for entry in result.roles:
            # Ignore an index the model invented or already answered.
            if entry.index in missing:
                resolved[entry.index] = entry.role_family

    return resolved
