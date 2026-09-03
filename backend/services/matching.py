"""Requirement matching: a master resume + a posting's requirements in, a
per-requirement verdict out.

The third AI integration, and the cheapest of the three. Parsing extracts, and
tailoring writes; this one only COMPARES two documents that are both already in
hand. That is retrieval and judgement against fixed evidence, not generation, so
it runs on the cheap model (settings.anthropic_model, Haiku) rather than the
top one that tailoring earns.

HTTP-ignorant like every service: plain arguments in, a FitReport or None out.

The never-invent guardrail from vision.md applies here in its own shape. The
parser must not fabricate a requirement the posting didn't state; the tailorer
must not fabricate resume content. This one must not fabricate EVIDENCE — it may
only cite what the master actually says, and when nothing supports a
requirement, the honest answer is "missing" with no citation.
"""

import logging
from datetime import date

from anthropic import Anthropic

from config import Settings
from schemas.fit import (
    FitReport,
    RequirementMatch,
    RequirementVerdicts,
)
from schemas.resume import Resume

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You judge how well a candidate's resume answers a job
posting's stated requirements.

You are given a RESUME as JSON and a numbered list of REQUIREMENTS taken from
one posting. For each requirement, return its index and one verdict:

- "met": the resume clearly shows this. Cite the specific experience, project,
  or skill in `evidence`.
- "partial": the resume shows something genuinely adjacent but not the thing
  asked for. Say what is there and what is short in `evidence`. Examples of
  adjacent: a required framework where the resume shows a different framework in
  the same language; three years asked for where the resume shows one.
- "missing": nothing in the resume supports it. Leave `evidence` null.
- "unstated": ELIGIBILITY ONLY (see below) — the resume does not cover this and
  no resume normally would. Say what the candidate needs to confirm in
  `evidence`.

There are TWO KINDS of requirement and they are judged differently. Deciding
which kind you are looking at is the first thing to do.

CAPABILITY requirements — skills, tools, technologies, kinds of experience.
Judge these strictly against what the resume shows.
- Never credit a skill because it is implied, adjacent, or commonly held. If the
  resume does not show it, it is "missing".
- Never answer "unstated" for a capability requirement. A skill the resume omits
  is missing, not unstated.
- Be strict. An honest "missing" is useful; a generous "met" is not. When torn
  between "met" and "partial", choose "partial". When torn between "partial" and
  "missing", choose "missing".
- BUT: when a requirement names its own examples and the resume shows those
  examples, it is "met", not "partial". "Familiarity with software testing
  fundamentals (unit testing, integration testing, regression testing)" is met
  by a resume showing unit, integration, and regression tests. Do not demand
  formality, vocabulary, or breadth the requirement did not ask for. The
  strictness above is about not crediting things the resume never shows, not
  about withholding credit for exactly what was asked.

ELIGIBILITY requirements — enrollment, degree program, graduation timing,
returning to study after the internship, work authorization, location. These are
plain facts about the person rather than evidence of skill, and a resume states
them directly. DERIVE the answer from the facts the resume states. Working out a
consequence of a stated fact is arithmetic, not inference about unstated
ability, and the strictness rule above does not apply to it.
- "Currently enrolled in a Bachelor's/Master's program": met when the education
  section shows a degree in progress. Cite it.
- "Must be returning to studies after the internship": met when the expected
  graduation date falls AFTER the upcoming internship period. Today's date is
  given below; compare it against the expected graduation date and say so.
- "Right to work without visa sponsorship", "must hold a security clearance",
  and similar status facts: judge against `contact.work_authorization` when the
  resume states it. When the resume says nothing about it, answer "unstated" and
  say what needs confirming. Do NOT answer "missing" — a blank field is not
  evidence that the candidate lacks the right.

Rules for every verdict:
- Return one entry per requirement, with the SAME index you were given.
- `evidence` must quote or closely paraphrase something actually present in the
  resume, or state plainly what is missing from it. Never invent a project,
  tool, metric, date, or claim to justify a verdict.
- Keep each `evidence` to one sentence."""


def assess_requirements(
    master: Resume,
    requirements: list[str],
    settings: Settings,
    max_rounds: int = 2,
    preferred: list[str] | None = None,
) -> FitReport | None:
    """Judge each requirement against the master resume.

    Returns None only when the model gives nothing back at all on the first
    round (a refusal, or a reply cut off before a complete object) — the route
    turns that into a 502. An empty requirements list returns an empty report
    rather than None, because "this posting stated no requirements" is a real
    answer and not a failure.

    Why the retry loop: the same partial-answer behavior services/parsing.py
    documents for classify_role_families — the model sometimes answers for part
    of a numbered list and stops cleanly, well inside max_tokens, so it is not
    truncation and a bigger budget does not fix it. Each round re-asks ONLY for
    the indices still missing, using their ORIGINAL numbering, so answers always
    map straight back.

    Anything still unanswered after the last round is recorded as "unknown"
    rather than dropped. Dropping it would shrink the denominator and quietly
    inflate how well you match.
    """
    # Required and preferred are judged IDENTICALLY and in one call — the same
    # question is being asked of both, and a second call would double the cost
    # to answer it. They are combined here and split apart again by index at the
    # end, which is also why the model is never told which is which: knowing an
    # item is merely preferred would invite it to grade that item more leniently.
    preferred = preferred or []
    all_items = [*requirements, *preferred]
    kinds: list[str] = ["required"] * len(requirements) + ["preferred"] * len(preferred)

    if not all_items:
        return FitReport.from_matches([])

    client = Anthropic(api_key=settings.anthropic_api_key)
    resolved: dict[int, tuple[str, str | None]] = {}

    resume_json = master.model_dump_json(indent=2)
    # Timing requirements ("must be returning to studies afterwards") cannot be
    # judged without knowing when now is — the resume gives a graduation date
    # and nothing to compare it against. The model has no reliable clock, so the
    # date is supplied rather than assumed.
    today = date.today().isoformat()

    for round_number in range(max_rounds):
        missing = [i for i in range(len(all_items)) if i not in resolved]
        if not missing:
            break

        # Numbered by ORIGINAL index, not by position within this round's
        # subset, so a second-round answer needs no re-mapping to be applied.
        numbered = "\n".join(f"{i}. {all_items[i]}" for i in missing)
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"TODAY'S DATE: {today}\n\n"
                        f"RESUME:\n{resume_json}\n\n"
                        f"REQUIREMENTS:\n{numbered}"
                    ),
                }
            ],
            output_format=RequirementVerdicts,
        )
        result = response.parsed_output
        if result is None:
            # Nothing at all on the first round means nothing to report. On a
            # later round, keep whatever earlier rounds already resolved.
            if round_number == 0:
                return None
            break

        for entry in result.verdicts:
            # Ignore an index the model invented or already answered.
            if entry.index in missing:
                resolved[entry.index] = (entry.verdict, entry.evidence)

    if len(resolved) < len(all_items):
        logger.warning(
            "Requirement matching answered %d of %d after %d rounds",
            len(resolved),
            len(all_items),
            max_rounds,
        )

    matches = []
    for i, item in enumerate(all_items):
        verdict, evidence = resolved.get(i, ("unknown", None))
        matches.append(
            RequirementMatch(
                requirement=item,
                verdict=verdict,  # type: ignore[arg-type]  # "unknown" is StoredVerdict-only
                evidence=evidence,
                kind=kinds[i],  # type: ignore[arg-type]
            )
        )

    return FitReport.from_matches(matches)
