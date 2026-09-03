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

Rules:
- Return one entry per requirement, with the SAME index you were given.
- Judge ONLY against what the resume actually says. Never credit a skill because
  it is implied, adjacent, or commonly held. If it is not in the resume, it is
  not met.
- `evidence` must quote or closely paraphrase something actually present in the
  resume. Never invent a project, tool, metric, or claim to justify a verdict.
- Be strict. An honest "missing" is useful; a generous "met" is not. When torn
  between "met" and "partial", choose "partial". When torn between "partial" and
  "missing", choose "missing".
- Requirements about degree, graduation timing, and authorization are judged the
  same way: against what the resume states, not what seems likely.
- Keep each `evidence` to one sentence."""


def assess_requirements(
    master: Resume,
    requirements: list[str],
    settings: Settings,
    max_rounds: int = 2,
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
    if not requirements:
        return FitReport.from_matches([])

    client = Anthropic(api_key=settings.anthropic_api_key)
    resolved: dict[int, tuple[str, str | None]] = {}

    resume_json = master.model_dump_json(indent=2)

    for round_number in range(max_rounds):
        missing = [i for i in range(len(requirements)) if i not in resolved]
        if not missing:
            break

        # Numbered by ORIGINAL index, not by position within this round's
        # subset, so a second-round answer needs no re-mapping to be applied.
        numbered = "\n".join(f"{i}. {requirements[i]}" for i in missing)
        response = client.messages.parse(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"RESUME:\n{resume_json}\n\nREQUIREMENTS:\n{numbered}",
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

    if len(resolved) < len(requirements):
        logger.warning(
            "Requirement matching answered %d of %d after %d rounds",
            len(resolved),
            len(requirements),
            max_rounds,
        )

    matches = []
    for i, requirement in enumerate(requirements):
        verdict, evidence = resolved.get(i, ("unknown", None))
        matches.append(
            RequirementMatch(
                requirement=requirement,
                verdict=verdict,  # type: ignore[arg-type]  # "unknown" is StoredVerdict-only
                evidence=evidence,
            )
        )

    return FitReport.from_matches(matches)
