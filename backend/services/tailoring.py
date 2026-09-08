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
import re

from anthropic import Anthropic

from config import Settings
from schemas.resume import Resume
from services.resume_render import (
    count_lines_containing,
    count_pages,
    count_skill_lines,
)

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
- Treat `activities` (leadership, clubs, tutoring) exactly like experience for
  selection and phrasing, with one difference: print at most 1 bullet per
  activity entry. It is the last and lowest-value section on the page.
  If the page is tight, drop the ENTIRE activities section rather than printing
  some of its entries. A half-printed section reads as a document that ran out of
  room; no section at all reads as a deliberate choice.
- For each entry you keep, select and reorder its bullets, strongest and most
  relevant first. Give every professional EXPERIENCE entry 4 bullets and every
  PROJECT 3. Drop below that only when the master genuinely has nothing worth the
  space, never to save room: the page is measured and trimmed after you return,
  so aiming high costs nothing and aiming low leaves the bottom of the page
  blank, which no later step can fix. Rephrase them into strong
  accomplishment bullets: lead with an action verb and state what was built and
  the result or impact (the "accomplished X by doing Y, measured by Z" pattern)
  whenever the facts already support it.
- Size every bullet to FILL the lines it occupies. Aim for two full lines, roughly
  38 to 46 words. A bullet that spills onto a third line to carry three words
  wastes a whole line, and one that stops halfway through its second line leaves a
  ragged gap; both read as unconsidered. If a bullet falls short, pull another
  real detail for that same entry from the master to fill it out rather than
  padding with adjectives. If it runs long, cut a clause, never a number.
- Write numbers as NUMERALS, not words: "4 import flows", not "four import
  flows". They scan faster and cost fewer characters. Percentages take the symbol.
- Reorder each project's `tools` list and each `skills` group so the most
  job-relevant items lead, then trim so each fits on ONE line: keep at most 6
  items per skills group and at most 5 tools per project. If an item contains a
  parenthetical list, keep at most two examples inside it, e.g. shorten
  "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" to "AWS (Lambda, DynamoDB)".
  Never add a tool not present in the master.
- Mark at most ONE fragment of each bullet as bold by wrapping it in double
  asterisks, like **this fragment**. Bold the single NUMBER that best shows scale
  or result, and keep the few words around it that make the number mean
  something: "**4% duplicate rate**", "**51% of signups**", "**~520 ms**". The
  number may describe the PROBLEM or the FIX, whichever is the more striking
  figure, so "**30 fake usage events per user per minute**" is a good span even
  though it names the bug.
  If a bullet contains no number worth showing, print it with NO bold at all. An
  unbolded bullet is correct and expected; do not reach for a phrase to bold
  instead. Someone skimming reads only the bold text, so the bold on a page
  should read as a list of figures.
  One span per bullet, never two. Keep it under about 8 words and never bold a
  whole bullet or a whole clause.
  EXCEPTION: bullets in `activities` never carry a bold span at all. Their
  numbers are small ones (a handful of students, a couple of events), and bolding
  a small number next to a page of percentages and millisecond timings drags the
  eye to the weakest figure on the resume and weakens every other span.

The final resume MUST fit on a single page, and it must also FILL that page. A
resume that stops three quarters of the way down looks like there was nothing
more to say, which is the opposite of the impression it exists to make. Those
pull against each other, so aim high and trust the counts above: overflow is
measured and trimmed after you return, but a short page is not fixed for you.

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
    # Same reasoning for the graduation-date choice: which of two true dates
    # prints is Lee's call per application, not something the model should infer
    # from a job description.
    result.grad_date_variant = master.grad_date_variant

    # Same reasoning, one level down: `descriptor` and `links` are fixed facts
    # about an entry, not content to be selected. Neither is mentioned in the
    # prompt and both default to empty, so the model drops them silently and the
    # tailored PDF loses the company descriptor and every repo link that the base
    # resume prints. Restored by identity rather than asked for, because a
    # missing link is invisible in review: the title still renders, it just stops
    # being clickable.
    master_descriptors = {e.organization: e.descriptor for e in master.experience}
    for entry in result.experience:
        if entry.organization in master_descriptors:
            entry.descriptor = master_descriptors[entry.organization]
    master_links = {p.name: p.links for p in master.projects}
    for project in result.projects:
        if project.name in master_links:
            project.links = master_links[project.name]

    # Enforce never-invent before anything else looks at the draft, so a
    # fabricated skill cannot survive into the PDF or a saved version.
    invented = strip_invented_entries(master, result)
    invented += strip_invented_skills(master, result)
    if invented:
        logger.warning(
            "Tailoring invented content not present in the master; removed: %s",
            "; ".join(invented),
        )

    # Measure before returning. The trim runs on the tailored draft, so the
    # reviewable JSON and the eventual PDF are the same thing — a resume that
    # looked fine in review and overflowed on download would defeat the point.
    # The prompt asks for one bold span per bullet; this makes it true. Models
    # over-emphasise, and a bullet with three bold phrases greys the page out and
    # destroys the only thing bold is for.
    over = cap_bold_spans(result)
    if over:
        logger.info("Tailoring over-bolded; capped to one span in: %s", "; ".join(over))

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
#
# This floor is the BACKSTOP for the prompt, not a target. The prompt asks for 3
# bullets on every experience entry and 2 on every project, deliberately more
# than the page may hold, because the pipeline can only ever remove: nothing here
# grows a resume that came back short, so a model told to be conservative leaves
# the bottom quarter of the page blank and no later step notices. Asking high and
# trimming down is the only direction that has a correction step.
#
# Note what that means for the cut order below: with projects sitting AT this
# floor, they are filtered out of `trimmable` entirely, so the 3rd experience
# bullet is the first thing any overflow takes. That is the right trade even
# though it undoes the extra bullet, because the alternative at that point is
# losing a whole project, and one bullet is the cheaper loss. It does mean the
# 3-bullet experience entry is a nice-to-have that only survives while the page
# has room for it.
_MIN_BULLETS_PER_ENTRY = 2
_MIN_PROJECTS = 2
# An activity entry earns one line of bullet, never two. Clubs and tutoring are
# supporting evidence; they do not get the same room as a job.
_MAX_ACTIVITY_BULLETS = 1

# Coursework is a supporting detail, not a selling point, so it gets one line and
# no more. Six courses wrapped to two on a real tailored resume, which spends a
# whole line of the page on the least specific content it carries.
_MAX_COURSEWORK_LINES = 1
# Never trim it away to nothing here — an empty coursework line is the page-fit
# loop's decision to make, not this one's.
_MIN_COURSEWORK = 1

# A skills row is one line. Two-line rows are the most expensive wrap on the
# page: they cost a line without adding a fact a reader weighs, and the line
# comes straight out of the bullets. Never trim a row to nothing — a category
# with no items is worse than a short one.
_MIN_SKILL_ITEMS = 3


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


# How many examples survive inside a parenthetical. Two reads as "and things
# like these"; four reads as a list and costs the width of a whole extra skill.
_MAX_PARENTHETICAL_EXAMPLES = 2


def _shorten_one_parenthetical(items: list[str]) -> tuple[str, str] | None:
    """Trim the widest over-long parenthetical in `items`. Mutates it.

    Returns (before, after) for logging, or None when there is nothing left to
    shorten — which is the signal to start dropping whole items instead.
    """
    candidates = [
        (i, item)
        for i, item in enumerate(items)
        if " (" in item
        and item.rstrip().endswith(")")
        and len(item.split(" (", 1)[1].rstrip(")").split(",")) > _MAX_PARENTHETICAL_EXAMPLES
    ]
    if not candidates:
        return None
    # Widest first: it is the one actually costing the line.
    index, item = max(candidates, key=lambda pair: len(pair[1]))
    base, rest = item.split(" (", 1)
    examples = [e.strip() for e in rest.rstrip(")").split(",")]
    kept = ", ".join(examples[:_MAX_PARENTHETICAL_EXAMPLES])
    items[index] = f"{base} ({kept})"
    return item, items[index]


def _trim_skills_to_one_line(resume: Resume) -> list[str]:
    """Drop the least relevant items until every skills row is one line. Mutates.

    Measured, not counted, for the same reason coursework is: whether a row wraps
    depends on the width of its strings, not their number. "AWS (IoT Core,
    Lambda, DynamoDB, API Gateway)" is worth four ordinary items on its own, so a
    fixed cap of six would be wrong in both directions.

    Cuts from the END, which is the relevance order both the master and the
    tailoring prompt maintain, so the least job-relevant item goes first.
    """
    cuts: list[str] = []
    while True:
        lines = count_skill_lines(resume)
        # Rows render in declaration order, so index i is skills[i]. A row that
        # is already one line, or already at the floor, is not a candidate.
        over = [
            i
            for i, n in enumerate(lines)
            if n > 1 and len(resume.skills[i].items) > _MIN_SKILL_ITEMS
        ]
        if not over:
            return cuts
        # Take from the worst offender first so one pathological row cannot make
        # every other row pay for it.
        target = resume.skills[max(over, key=lambda i: lines[i])]

        # Shorten a long parenthetical BEFORE dropping any item. One entry like
        # "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" is as wide as four
        # ordinary skills, so trimming its examples buys back the line while
        # costing nothing a reader weighs — whereas dropping items would spend
        # GitHub Actions and Cloudflare Tunnel to keep four AWS service names.
        # Same rule the tailoring prompt gives the model, applied where the base
        # resume can reach it too.
        shortened = _shorten_one_parenthetical(target.items)
        if shortened is not None:
            before, after = shortened
            cuts.append(f"shortened {before} to {after} in {target.category}")
            continue

        dropped = target.items.pop()
        cuts.append(f"dropped skill: {dropped} from {target.category}")


def fit_to_one_page(resume: Resume) -> tuple[Resume, list[str]]:
    """Trim `resume` until it renders to one page. Returns the copy and the cuts.

    Cut order, cheapest loss first:

    0. Coursework AND every skills row down to a single line, applied ALWAYS
       rather than only on overflow: neither earns a second line even when there
       is room, and a wrapped skills row costs a bullet for nothing.
    1. The LAST bullet of whichever entry has the most, down to a floor of two.
       Last is principled rather than arbitrary: tailoring returns each entry's
       bullets in its own relevance order, strongest first, so the last bullet of
       the longest list is the least relevant line on the page. Ties go to a
       project over a job, because work experience outranks a side project.
    2. Coursework, which is one line of six course names and the least specific
       content on the page.
    3. The activities section, whole and never in part.
    4. The last project entirely, down to a floor of two, since projects arrive
       in relevance order too.

    If it still does not fit, it gives up and returns what it has along with the
    cuts it made. Returning a two-page resume that the caller can see is honest;
    quietly hacking it down to one page is not.
    """
    work = resume.model_copy(deep=True)
    cuts: list[str] = []

    # Always, whether or not the resume overflows: coursework earns one line.
    cuts.extend(_trim_coursework_to_one_line(work))

    # Always, same reasoning: so does every skills row.
    cuts.extend(_trim_skills_to_one_line(work))

    # Always: an activity prints at most one bullet. The prompt asks for this and
    # the model mostly complies, but a second bullet on a club entry costs the
    # same line as a second bullet on a job, and it is not worth the same.
    for activity in work.activities:
        if len(activity.bullets) > _MAX_ACTIVITY_BULLETS:
            activity.bullets = activity.bullets[:_MAX_ACTIVITY_BULLETS]
            cuts.append(f"trimmed {activity.organization} to one bullet")

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

        # 3. The activities section, WHOLE. Never a single entry out of it: a
        # section showing one of two clubs reads as a document that ran out of
        # room, while no section at all reads as a choice. It goes before any
        # project is cut because it is the lowest-value block on the page.
        if work.activities:
            dropped = ", ".join(a.organization for a in work.activities)
            work.activities = []
            cuts.append(f"dropped the activities section ({dropped})")
            continue

        # 4. The least relevant project, whole.
        if len(work.projects) > _MIN_PROJECTS:
            dropped = work.projects.pop()
            cuts.append(f"dropped the {dropped.name} project")
            continue

        # Nothing left that can be cut without gutting it.
        break

    return work, cuts


# --- Bold-span enforcement ---------------------------------------------------
# Emphasis is the ONE piece of presentation the model is allowed to choose,
# because unlike layout it genuinely should change per job: a backend posting
# wants the idempotency bolded, a frontend posting wants the optimistic update.
# A <strong> cannot alter margins, page count, or the grid, so the locked
# template still owns every part of the format that matters.
#
# What the model gets wrong is the COUNT, not the choice — it emphasises three
# phrases per bullet given the chance, and bold that covers half the page stops
# being a highlight. So the prompt asks and this function enforces, the same
# division of labour as strip_invented_skills below: the model judges, the code
# guarantees.
#
# Note this is deliberately NOT an anti-invention guard. Bullets are already
# rephrasable, so wrapping words in asterisks opens no smuggling route that
# rewriting the sentence did not already open; the never-invent rule covers the
# text either way. This function only fixes the count and cleans up markers.
_BOLD_SPAN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _cap_one_span(text: str) -> str:
    """Keep the first **bold** span in `text`; unwrap the rest.

    Also drops any leftover unpaired "**", which would otherwise reach the PDF as
    literal asterisks: the renderer's bold filter only converts matched pairs.
    """
    out: list[str] = []
    last = 0
    kept = False
    for m in _BOLD_SPAN.finditer(text):
        out.append(text[last : m.start()].replace("**", ""))
        if kept or not m.group(1).strip():
            out.append(m.group(1))     # unwrap: extra span, or an empty one
        else:
            out.append(m.group(0))     # keep the first real span intact
            kept = True
        last = m.end()
    out.append(text[last:].replace("**", ""))
    return "".join(out)


def cap_bold_spans(tailored: Resume) -> list[str]:
    """Enforce at most one bold span per bullet, in place.

    Returns a short label for each bullet that had to be changed, for logging.
    """
    changed: list[str] = []
    entries = [(x.organization, x) for x in tailored.experience]
    entries += [(p.name, p) for p in tailored.projects]
    for label, entry in entries:
        for i, bullet in enumerate(entry.bullets):
            capped = _cap_one_span(bullet)
            if capped != bullet:
                entry.bullets[i] = capped
                changed.append(f"{label} bullet {i + 1}")

    # Activities carry NO bold at all, so they get stripped rather than capped.
    # The prompt says so and the master seeds a counter-example (the tutoring
    # bullet banks "**3 students**"), which is exactly the setup where asking
    # nicely fails: a small number bolded beside a page of percentages and
    # millisecond timings pulls the eye to the weakest figure on the resume.
    for activity in tailored.activities:
        for i, bullet in enumerate(activity.bullets):
            stripped = _BOLD_SPAN.sub(r"\1", bullet)
            if stripped != bullet:
                activity.bullets[i] = stripped
                changed.append(f"{activity.organization} bullet {i + 1} (bold removed)")
    return changed


# --- Never-invent enforcement ------------------------------------------------
# The system prompt forbids inventing in three separate sentences and the model
# still does it: a Mastercard posting listing "Java, Python, C++, JavaScript"
# among its requirements produced a resume claiming Java, which is nowhere in the
# master, plus a "Concepts" skills category that does not exist. Non-determinism
# means it holds most of the time and fails some of the time, which is the worst
# case — a false claim on a resume Lee sends out.
#
# So the rule is checked rather than requested. Anything not traceable to the
# master is removed. Removal, never substitution: this can make a resume thinner,
# never wronger.


def _normalize(value: str) -> str:
    """Casefold and strip non-alphanumerics, so "Cloud & DevOps" == "cloud devops"."""
    return "".join(c for c in value.casefold() if c.isalnum())


def _split_parenthetical(item: str) -> tuple[str, set[str]]:
    """"AWS (Lambda, DynamoDB)" -> ("aws", {"lambda", "dynamodb"})."""
    base, _, rest = item.partition(" (")
    inner = rest.rstrip(")") if rest else ""
    examples = {_normalize(x) for x in inner.split(",") if x.strip()}
    return _normalize(base), examples


def _is_traceable(item: str, master_items: list[str]) -> bool:
    """True when `item` is a master item, or a narrowing of one.

    The narrowing case is required by the prompt itself, which tells the model to
    shorten "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" to "AWS (Lambda,
    DynamoDB)". That is a legitimate trim, not an invention, so an item matches
    when its base name matches and its parenthetical examples are a SUBSET of the
    master's. A new example inside the parentheses is still an invention.
    """
    base, examples = _split_parenthetical(item)
    for candidate in master_items:
        candidate_base, candidate_examples = _split_parenthetical(candidate)
        if base == candidate_base and examples <= candidate_examples:
            return True
    return False


def strip_invented_entries(master: Resume, tailored: Resume) -> list[str]:
    """Remove whole entries with no counterpart in the master. Mutates `tailored`.

    The sibling of strip_invented_skills, one level up. That one guards the
    CONTENTS of an entry (skill items, project tools); nothing guarded the
    entries themselves, so an entire fabricated job could reach the PDF while
    every skill on the page checked out.

    The real failure: a tailored resume grew a second EXPERIENCE entry reading
    "University of Florida / B.S. Computer Engineering / Expected May 2029" with
    no bullets. The model had copied the education record into the experience
    list, filling the required `role` field with the degree name. Every
    individual skill was traceable, so the existing guard passed it through, and
    the template renders whatever is in `experience`.

    Matching is on the IDENTITY field only, the one the prompt already forbids
    changing: organization for a job, name for a project, institution for a
    school. Bullets are rephrasable by design, so comparing them would reject
    legitimate work.

    Removal, never substitution, same as strip_invented_skills: this can make a
    resume thinner, never wronger. Note the corollary, which matters when reading
    a bug report: an entry that IS in the master survives this function. If a
    stray entry was typed into the master itself, it is real data as far as
    tailoring is concerned, and the fix is in the master, not here.
    """
    removed: list[str] = []

    def keep(entries: list, master_entries: list, field: str, kind: str) -> list:
        allowed = {_normalize(getattr(e, field)) for e in master_entries}
        surviving = []
        for entry in entries:
            identity = getattr(entry, field)
            if _normalize(identity) in allowed:
                surviving.append(entry)
            else:
                removed.append(f"{kind} '{identity}' (not in master)")
        return surviving

    tailored.experience = keep(
        tailored.experience, master.experience, "organization", "experience entry"
    )
    tailored.projects = keep(tailored.projects, master.projects, "name", "project")
    tailored.activities = keep(
        tailored.activities, master.activities, "organization", "activity"
    )
    tailored.education = keep(
        tailored.education, master.education, "institution", "education entry"
    )
    return removed


def strip_invented_skills(master: Resume, tailored: Resume) -> list[str]:
    """Remove skills and tools with no basis in the master. Mutates `tailored`.

    An item counts as traceable if it appears ANYWHERE in the master — a skills
    row or any project's tools — because promoting a tool Lee really used into
    the skills list is a presentation choice, while adding one he never listed is
    a lie. Categories must match a master category: a whole invented group is how
    "Concepts" appeared.
    """
    removed: list[str] = []

    master_items = [item for group in master.skills for item in group.items]
    master_items += [tool for project in master.projects for tool in project.tools]
    master_categories = {_normalize(g.category): g.category for g in master.skills}

    kept_groups = []
    for group in tailored.skills:
        if _normalize(group.category) not in master_categories:
            removed.append(f"skills category '{group.category}' (not in master)")
            continue
        # Keep the master's spelling of the category, so tailoring cannot quietly
        # rename a section either.
        group.category = master_categories[_normalize(group.category)]
        surviving = []
        for item in group.items:
            if _is_traceable(item, master_items):
                surviving.append(item)
            else:
                removed.append(f"skill '{item}' in {group.category}")
        group.items = surviving
        kept_groups.append(group)
    tailored.skills = kept_groups

    for project in tailored.projects:
        master_tools = [
            tool
            for master_project in master.projects
            if master_project.name == project.name
            for tool in master_project.tools
        ]
        surviving = []
        for tool in project.tools:
            if _is_traceable(tool, master_tools):
                surviving.append(tool)
            else:
                removed.append(f"tool '{tool}' on {project.name}")
        project.tools = surviving

    return removed
