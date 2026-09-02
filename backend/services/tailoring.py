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

import logging

from anthropic import Anthropic

from config import Settings
from schemas.resume import Resume
from services.resume_render import count_lines_containing, count_pages

logger = logging.getLogger(__name__)

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

The final resume MUST fit on a single page. It is better to cut a weaker bullet
or project than to overflow. When in doubt, cut.

What you MUST NOT do — these are hard rules, never break them:
- NEVER invent. Do not add any metric, number, technology, tool, company, date,
  or claim that is not already present in the master. If a bullet has no metric,
  do not fabricate one; a strong bullet without a number is fine.
- Never write a `summary`. This resume has no summary section: leave the field
  empty (null) even if the job description asks for a profile or objective.
- Never change identity facts: name, contact, education (institution, degree,
  GPA, honors, dates), organization names, roles, or project names.
- Do not use em dashes. Rephrase with commas or shorter sentences. Ordinary
  hyphens inside words such as "full-stack" or "on-device" are fine.

Return only the tailored resume in the required schema."""


def tailor_resume(
    master: Resume, job_description: str, settings: Settings
) -> Resume | None:
    """Tailor `master` to `job_description`, or None if Claude can't.

    The result is guaranteed to render to one page where that is achievable
    without gutting it: the model's draft is measured and trimmed by
    `fit_to_one_page` before it is returned, because the model cannot see a
    rendered page and consistently overshoots on volume. What was cut is logged.

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
    result = response.parsed_output
    if result is None:
        return None

    # career_stage is a fixed rendering setting, not content. The model could
    # omit it (it then defaults to "student") or guess it, so we overwrite it
    # from the master — a professional resume must never silently revert to
    # the student layout after tailoring.
    result.career_stage = master.career_stage

    # Measure before returning. The trim runs on the tailored draft, so the
    # reviewable JSON and the eventual PDF are the same thing — a resume that
    # looked fine in review and overflowed on download would defeat the point.
    fitted, cuts = fit_to_one_page(result)
    if cuts:
        logger.info(
            "Tailored resume ran long; trimmed to fit one page: %s", "; ".join(cuts)
        )
    return fitted


# --- One-page fit ------------------------------------------------------------
# The prompt asks for one page and the model cooperates on bullet LENGTH, but it
# cannot see a rendered page, so it misjudges VOLUME. Measured on a real tailor
# against a Stripe posting: every bullet landed inside the 20-to-28-word target
# and the resume still came to two pages, because 13 bullets at that length do
# not fit however well each one is written.
#
# So the guarantee is enforced here instead of asked for: render, measure, cut
# the weakest thing, measure again. No API call is involved, so this is cheap and
# deterministic, and it cannot make the resume worse in a way review would not
# catch — every cut is a removal, never a rewrite.

# How far trimming may go before it would start gutting the resume rather than
# tightening it. Below these, a resume is better off overflowing and being fixed
# by hand than silently reduced to a stub.
_MIN_BULLETS_PER_ENTRY = 2
_MIN_PROJECTS = 2

# Coursework is a supporting detail, not a selling point, so it gets one line and
# no more. Six courses wrapped to two on a real tailored resume, which spends a
# whole line of the page on the least specific content it carries.
_MAX_COURSEWORK_LINES = 1
# Never trim it away to nothing here — an empty coursework line is the page-fit
# loop's decision to make, not this one's.
_MIN_COURSEWORK = 1


def _trim_coursework_to_one_line(resume: Resume) -> list[str]:
    """Drop the least relevant courses until the line stops wrapping. Mutates.

    Tailoring returns coursework already ordered by relevance to the job, so the
    courses at the end are the ones the job cares least about — the same logic
    that makes the last bullet the right one to cut.

    Measured rather than counted: whether six courses wrap depends on how long
    their names are ("Data Structures and Algorithms" is three times the width of
    "Digital Logic"), so a fixed cap of four would be wrong in both directions.
    """
    cuts: list[str] = []
    while (
        count_lines_containing(resume, "Coursework") > _MAX_COURSEWORK_LINES
        and sum(len(e.coursework) for e in resume.education) > _MIN_COURSEWORK
    ):
        # Take from whichever entry has the most, so two schools stay balanced.
        target = max(resume.education, key=lambda e: len(e.coursework))
        if not target.coursework:
            break
        dropped = target.coursework.pop()
        cuts.append(f"dropped coursework: {dropped}")
    return cuts


def fit_to_one_page(resume: Resume) -> tuple[Resume, list[str]]:
    """Trim `resume` until it renders to one page. Returns the copy and the cuts.

    Cut order, cheapest loss first:

    0. Coursework down to a single line, applied ALWAYS rather than only on
       overflow: it is the least specific content on the page and does not earn
       a second line even when there is room.
    1. The LAST bullet of whichever entry has the most, down to a floor of two.
       Last is principled rather than arbitrary: tailoring returns each entry's
       bullets in its own relevance order, strongest first, so the last bullet of
       the longest list is the least relevant line on the page. Ties go to a
       project over a job, because work experience outranks a side project.
    2. Coursework, which is one line of six course names and the least specific
       content on the page.
    3. The last project entirely, down to a floor of two, since projects arrive
       in relevance order too.

    If it still does not fit, it gives up and returns what it has along with the
    cuts it made. Returning a two-page resume that the caller can see is honest;
    quietly hacking it down to one page is not.
    """
    work = resume.model_copy(deep=True)
    cuts: list[str] = []

    # Always, whether or not the resume overflows: coursework earns one line.
    cuts.extend(_trim_coursework_to_one_line(work))

    while count_pages(work) > 1:
        # 1. Trim the longest bullet list that is still above the floor. The sort
        # key puts the longest list first and, at equal length, a project ahead of
        # a job.
        trimmable = [
            (len(entry.bullets), is_project, label, entry)
            for entry, is_project, label in (
                [(e, 0, e.organization) for e in work.experience]
                + [(p, 1, p.name) for p in work.projects]
            )
            if len(entry.bullets) > _MIN_BULLETS_PER_ENTRY
        ]
        if trimmable:
            trimmable.sort(key=lambda t: (t[0], t[1]), reverse=True)
            _, _, label, entry = trimmable[0]
            entry.bullets.pop()
            cuts.append(f"dropped the last bullet from {label}")
            continue

        # 2. Coursework: one line, and the least specific thing on the page.
        if any(e.coursework for e in work.education):
            for education in work.education:
                education.coursework = []
            cuts.append("dropped the coursework line")
            continue

        # 3. The least relevant project, whole.
        if len(work.projects) > _MIN_PROJECTS:
            dropped = work.projects.pop()
            cuts.append(f"dropped the {dropped.name} project")
            continue

        # Nothing left that can be cut without gutting it.
        break

    return work, cuts
