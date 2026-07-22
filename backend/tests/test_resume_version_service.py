"""Tests for the resume version persistence service.

Service-level, like test_application_service.py: real (in-memory) DB via the `db`
fixture, no network. We assert that saving round-trips the resume through the
JSON column back into a Resume, that listing returns newest-first, and that a
list for an application with no versions is empty.
"""

from schemas.resume import Contact, Resume
from schemas.resume_version import ResumeVersionCreate
from services.resume_version import list_resume_versions, save_resume_version


def _sample_create(app_id: str, summary: str) -> ResumeVersionCreate:
    return ResumeVersionCreate(
        application_id=app_id,
        resume=Resume(contact=Contact(name="Lee"), summary=summary),
        job_description="Backend internship, Python and AWS.",
    )


def test_save_persists_and_round_trips_resume(db) -> None:
    row = save_resume_version(db, _sample_create("app-1", "Tailored summary."))

    assert row.id is not None
    assert row.application_id == "app-1"
    # Stored as a dict in the JSON column...
    assert row.resume_json["summary"] == "Tailored summary."
    # ...and it validates back into a Resume unchanged.
    restored = Resume.model_validate(row.resume_json)
    assert restored.summary == "Tailored summary."
    assert restored.contact.name == "Lee"


def test_list_returns_newest_first(db) -> None:
    first = save_resume_version(db, _sample_create("app-1", "first"))
    second = save_resume_version(db, _sample_create("app-1", "second"))

    versions = list_resume_versions(db, "app-1")

    assert [v.id for v in versions] == [second.id, first.id]


def test_list_is_empty_for_application_without_versions(db) -> None:
    save_resume_version(db, _sample_create("app-1", "only"))

    assert list_resume_versions(db, "app-2") == []
