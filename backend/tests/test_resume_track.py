"""Tests for the two resume flavours: software and embedded.

The rule was checked against the two base resumes Lee had already built by
hand, and it reproduces both exactly. That mattered more than elegance: a rule
derived from each project's tools looked obvious and got it wrong, because the
embedded resume keeps MILES second despite it carrying no embedded work at all.
It is there because it is the strongest project regardless of audience, which is
a judgement no heuristic was going to make.
"""

from schemas.resume import Contact, Project, Resume, SkillGroup
from services.resume import select_for_track


def _resume(projects: list[Project], skills: list[SkillGroup] | None = None) -> Resume:
    return Resume(contact=Contact(name="Lee"), projects=projects, skills=skills or [])


def _p(name: str, tracks: list[str] | None = None) -> Project:
    return Project(name=name, tracks=tracks or [], bullets=["did a thing"])


# --- Projects: filtered and reordered ----------------------------------------


def test_a_tagged_project_leads() -> None:
    """Tagging is a statement that this is the one to open with."""
    resume = _resume([_p("Prowl"), _p("MILES"), _p("FormFactor", ["embedded"])])

    chosen = select_for_track(resume, "embedded")

    assert [p.name for p in chosen.projects] == ["FormFactor", "Prowl", "MILES"]


def test_a_project_tagged_for_another_track_is_dropped() -> None:
    # The same statement that makes it lead on one resume says it is specific to
    # that reader, so it has no business on the other.
    resume = _resume([_p("Prowl", ["swe"]), _p("MILES"), _p("FormFactor", ["embedded"])])

    assert [p.name for p in select_for_track(resume, "embedded").projects] == [
        "FormFactor",
        "MILES",
    ]


def test_an_untagged_project_appears_on_both_and_keeps_its_place() -> None:
    """Empty means every flavour, which is the right default.

    Most projects are worth showing whoever is reading, and requiring a tag on
    each would make adding one a two-step job you would forget half the time.
    """
    resume = _resume([_p("MILES"), _p("MotionSense")])

    for track in ("swe", "embedded"):
        assert [p.name for p in select_for_track(resume, track).projects] == [
            "MILES",
            "MotionSense",
        ]


def test_two_tags_reproduce_both_hand_built_resumes() -> None:
    """The case the whole design was checked against.

    Master order is MILES, Prowl, MotionSense, FormFactor. Tagging exactly two
    projects yields both curated selections, in the right order, with no
    per-track lists to keep in step.
    """
    resume = _resume(
        [_p("MILES"), _p("Prowl", ["swe"]), _p("MotionSense"), _p("FormFactor", ["embedded"])]
    )

    swe = [p.name for p in select_for_track(resume, "swe").projects][:3]
    embedded = [p.name for p in select_for_track(resume, "embedded").projects][:3]

    assert swe == ["Prowl", "MILES", "MotionSense"]
    assert embedded == ["FormFactor", "MILES", "MotionSense"]


# --- Skills: promoted, never dropped -----------------------------------------


def test_a_tagged_skills_row_is_promoted_behind_the_first() -> None:
    """Behind the first, not in front of it.

    Languages leads on every engineering resume. The hardware row is the
    differentiator, not the headline.
    """
    resume = _resume(
        [],
        [
            SkillGroup(category="Languages", items=["C", "Python"]),
            SkillGroup(category="Frameworks", items=["React"]),
            SkillGroup(category="Hardware & Embedded", items=["STM32"], tracks=["embedded"]),
        ],
    )

    chosen = select_for_track(resume, "embedded")

    assert [row.category for row in chosen.skills] == [
        "Languages",
        "Hardware & Embedded",
        "Frameworks",
    ]


def test_a_skills_row_is_never_dropped_for_the_wrong_track() -> None:
    """The asymmetry with projects, and the reason for it.

    Dropping a project the reader does not care about buys space on a one-page
    resume. Dropping a skills row just hides something you can do, so an
    embedded resume still lists the web stack — it simply does not lead with it.
    """
    resume = _resume(
        [],
        [
            SkillGroup(category="Languages", items=["C"]),
            SkillGroup(category="Hardware & Embedded", items=["STM32"], tracks=["embedded"]),
        ],
    )

    assert [row.category for row in select_for_track(resume, "swe").skills] == [
        "Languages",
        "Hardware & Embedded",
    ]


def test_an_empty_skills_list_does_not_blow_up() -> None:
    assert select_for_track(_resume([]), "embedded").skills == []


# --- The master is a bank and must survive intact ----------------------------


def test_selecting_never_touches_the_master() -> None:
    """The master holds everything; a flavour is a view of it.

    Mutating it here would quietly delete the other track's work, which is the
    one thing the whole bullet-bank arrangement exists to prevent.
    """
    resume = _resume([_p("Prowl", ["swe"]), _p("FormFactor", ["embedded"])])

    select_for_track(resume, "swe")

    assert [p.name for p in resume.projects] == ["Prowl", "FormFactor"]
