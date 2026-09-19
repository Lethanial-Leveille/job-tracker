"""Tests for merging the YAML master resume into the stored one.

This decides what the resume actually says, and it runs unattended on every
deploy, so the failure mode is silent and expensive: a bullet you wrote into the
builder disappearing because a file that never knew about it won.

The merge exists because the master has two editors. A plain load refuses
whenever the database holds a bullet the YAML lacks — correct for a human at a
terminal, useless on a deploy, where it would either fail the deployment or skip
the load forever and the YAML edit would never reach you.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from load_master_from_yaml import _merge_bullets  # noqa: E402


def _resume(
    bullets: list[str],
    project_bullets: list[str] | None = None,
    activity_bullets: list[str] | None = None,
) -> dict:
    return {
        "experience": [{"organization": "Fuzzy AI", "bullets": list(bullets)}],
        "projects": [{"name": "Prowl", "bullets": list(project_bullets or [])}],
        "activities": [{"organization": "ACM", "bullets": list(activity_bullets or [])}],
    }


def test_a_builder_only_bullet_survives_the_load() -> None:
    """The whole reason this function exists.

    Five real bullets sat only in the database, written in the resume builder
    and never copied down. A plain load would have destroyed them.
    """
    stored = _resume(["typed into the builder", "shared"])
    incoming = _resume(["shared", "written in the yaml"])

    rescued = _merge_bullets(stored, incoming)

    assert rescued == 1
    assert "typed into the builder" in incoming["experience"][0]["bullets"]
    assert "written in the yaml" in incoming["experience"][0]["bullets"]


def test_the_yaml_keeps_its_own_ordering() -> None:
    """Rescued bullets are appended, not interleaved.

    The master is a bullet bank rather than a finished document — tailoring
    selects from it — so order within an entry decides nothing, and appending
    leaves the file's own ordering intact for the bullets it does carry.
    """
    stored = _resume(["from the builder"])
    incoming = _resume(["first", "second"])

    _merge_bullets(stored, incoming)

    assert incoming["experience"][0]["bullets"] == ["first", "second", "from the builder"]


def test_a_bullet_in_both_is_not_duplicated() -> None:
    stored = _resume(["same text"])
    incoming = _resume(["same text"])

    assert _merge_bullets(stored, incoming) == 0
    assert incoming["experience"][0]["bullets"] == ["same text"]


def test_projects_are_rescued_too_not_just_experience() -> None:
    # Both sections are editable in the builder, and only experience was
    # exercised by the case that prompted this.
    stored = _resume([], ["a project bullet from the builder"])
    incoming = _resume([], ["a project bullet from the yaml"])

    _merge_bullets(stored, incoming)

    assert len(incoming["projects"][0]["bullets"]) == 2


def test_an_entry_the_yaml_does_not_have_is_left_alone() -> None:
    """Merge adds bullets to entries the YAML carries; it does not resurrect
    whole entries.

    An employer removed from the file is a deliberate removal, and re-adding it
    every deploy would make the file impossible to edit down.
    """
    stored = {"experience": [{"organization": "Old Job", "bullets": ["x"]}], "projects": []}
    incoming = {"experience": [], "projects": []}

    assert _merge_bullets(stored, incoming) == 0
    assert incoming["experience"] == []


def test_merge_cannot_delete_which_is_the_stated_cost() -> None:
    """Pinning the limitation so it stays a known trade rather than a surprise.

    Removing a bullet from the YAML does NOT remove it from the stored resume,
    because merge cannot tell a deletion from a bullet the builder added. To
    actually delete one, edit it in the builder or run the load with --force.
    """
    stored = _resume(["a bullet being deleted from the yaml"])
    incoming = _resume([])

    _merge_bullets(stored, incoming)

    assert incoming["experience"][0]["bullets"] == ["a bullet being deleted from the yaml"]


def test_activities_are_rescued_too() -> None:
    """The regression. Activities were missing from the bullet index entirely.

    --merge runs unattended on every push, so an activity bullet typed into the
    builder was destroyed by the next deploy while an experience bullet typed
    the same way survived. Found 2026-09-19 when ACM was added.
    """
    stored = _resume([], activity_bullets=["typed into the builder"])
    incoming = _resume([], activity_bullets=["written in the yaml"])

    rescued = _merge_bullets(stored, incoming)

    assert rescued == 1
    assert incoming["activities"][0]["bullets"] == [
        "written in the yaml",
        "typed into the builder",
    ]


def test_an_org_that_is_both_an_employer_and_an_activity_does_not_cross_over() -> None:
    """Experience and activities are BOTH keyed by `organization`.

    So the index key has to carry the section too, or a company Lee worked for
    that shares a name with a club would swap bullets between the two — which
    would put a job bullet in the activities section and vice versa.
    """
    same = "Fuzzy AI"
    stored = {
        "experience": [{"organization": same, "bullets": ["a job bullet"]}],
        "projects": [],
        "activities": [{"organization": same, "bullets": ["a club bullet"]}],
    }
    incoming = {
        "experience": [{"organization": same, "bullets": []}],
        "projects": [],
        "activities": [{"organization": same, "bullets": []}],
    }

    _merge_bullets(stored, incoming)

    assert incoming["experience"][0]["bullets"] == ["a job bullet"]
    assert incoming["activities"][0]["bullets"] == ["a club bullet"]


def test_an_activity_the_yaml_does_not_have_is_left_alone() -> None:
    """Same rule activities now inherit from experience: merge adds bullets to
    entries the YAML carries, it does not resurrect whole entries.

    A club dropped from the file is a deliberate removal.
    """
    stored = {
        "experience": [],
        "projects": [],
        "activities": [{"organization": "Old Club", "bullets": ["x"]}],
    }
    incoming = {"experience": [], "projects": [], "activities": []}

    assert _merge_bullets(stored, incoming) == 0
    assert incoming["activities"] == []
