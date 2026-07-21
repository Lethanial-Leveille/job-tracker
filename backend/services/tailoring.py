"""Resume tailoring: a master Resume + a job description in, a tailored Resume out.

This is the AI half of the resume design (vision.md). Claude rewrites CONTENT
ONLY — it selects, reorders, and rephrases what is already in the master — and
returns the same Resume shape, which flows straight into the locked renderer
(services/resume_render.py). Because the output is the same schema, nothing
downstream changes: tailor, then render, and out comes a styled one-page PDF.

Model: the top model (Opus 4.8), not the cheap Haiku the parser uses. Vision
policy reserves the top model for exactly this — bullet selection and phrasing
is the judgment-heavy, highest-leverage step.

Method: structured outputs (`client.messages.parse(output_format=Resume)`), the
same pattern as the parser. The SDK forces the reply into the Resume schema and
validates it, so there is no hand-parsing and a malformed tailoring fails loudly.

HARD GUARDRAIL (hard rule #2, never invent resume content): the prompt forbids
adding any metric, technology, or claim not already in the master. Tailoring may
drop, reorder, and rephrase; it may never fabricate. The renderer can't invent
because it can't write content; the tailorer can't invent because it's told not
to and only ever sees the master's own facts.
"""

from anthropic import Anthropic

from config import Settings
from schemas.resume import Resume

# The prompt encodes the tailoring rules Lee asked for (one page, XYZ bullets,
# reorder projects, trim tool lists to one line, no em dashes) AND the never-
# invent guardrail. The schema (passed as output_format) constrains the shape;
# this prompt constrains the behavior.
_SYSTEM_PROMPT = """You tailor a master resume to a specific job description.

You are given a MASTER resume as JSON and a JOB DESCRIPTION. Return a tailored
resume in the SAME schema, optimized for this job.

What you MAY do:
- Reorder `experience` and `projects` so the most relevant to this job come
  first.
- Drop the least relevant projects so the whole resume fits on ONE page. Keep at
  most the 3 strongest, most relevant projects. Always keep every professional
  experience entry.
- For each entry you keep, select and reorder its bullets, keeping ONLY the 2 to
  3 strongest and most relevant. Rephrase them into strong accomplishment
  bullets: lead with an action verb and state what was built and the result or
  impact (the "accomplished X by doing Y, measured by Z" pattern) whenever the
  facts already support it. Keep each bullet concise, ideally a single line of
  roughly 20 to 28 words.
- Reorder each project's `tools` list and each `skills` group so the most
  job-relevant items lead, then trim so each fits on ONE line: keep at most 6
  items per skills group and at most 5 tools per project. If an item contains a
  parenthetical list, keep at most two examples inside it, e.g. shorten
  "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" to "AWS (Lambda, DynamoDB)".
  Never add a tool not present in the master.
- Rewrite the `summary` to target this job, in one to two sentences.

The final resume MUST fit on a single page. It is better to cut a weaker bullet
or project than to overflow. When in doubt, cut.

What you MUST NOT do — these are hard rules, never break them:
- NEVER invent. Do not add any metric, number, technology, tool, company, date,
  or claim that is not already present in the master. If a bullet has no metric,
  do not fabricate one; a strong bullet without a number is fine.
- Never change identity facts: name, contact, education (institution, degree,
  GPA, honors, dates), organization names, roles, or project names.
- Do not use em dashes. Rephrase with commas or shorter sentences. Ordinary
  hyphens inside words such as "full-stack" or "on-device" are fine.

Return only the tailored resume in the required schema."""


def tailor_resume(
    master: Resume, job_description: str, settings: Settings
) -> Resume | None:
    """Tailor `master` to `job_description`, or None if Claude can't.

    Returns None when the model declines or the reply is truncated before a
    complete object (the SDK surfaces both as parsed_output=None). Network or
    auth failures raise; the route decides how to present them.
    """
    client = Anthropic(api_key=settings.anthropic_api_key)
    user_content = (
        "MASTER RESUME (JSON):\n"
        f"{master.model_dump_json(indent=2)}\n\n"
        "JOB DESCRIPTION:\n"
        f"{job_description}"
    )
    response = client.messages.parse(
        model=settings.anthropic_tailoring_model,
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_format=Resume,
    )
    return response.parsed_output
