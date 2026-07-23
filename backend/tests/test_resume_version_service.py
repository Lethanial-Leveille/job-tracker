"""Tests for the resume version persistence service.

Service-level, like test_application_service.py: real (in-memory) DB via the `db`
fixture, no network. We assert that saving round-trips the resume through the
JSON column back into a Resume, that listing returns newest-first, that a list
for an application with no versions is empty, and that versions are scoped to
their owner.
"""

from models.user import User
from schemas.resume import Contact, Resume
from schemas.resume_version import ResumeVersionCreate
from services.resume_version import list_resume_versions, save_resume_version


def _sample_create(app_id: str, summary: str) -> ResumeVersionCreate:
    return ResumeVersionCreate(
        application_id=app_id,
        resume=Resume(contact=Contact(name="Lee"), summary=summary),
        job_description="Backend internship, Python and AWS.",
    )


def _other_user(db) -> User:
    row = User(email="other@example.com", password_hash="placeholder-not-a-hash")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_save_persists_and_round_trips_resume(db, user) -> None:
    row = save_resume_version(db, _sample_create("app-1", "Tailored summary."), user.id)

    assert row.id is not None
    assert row.application_id == "app-1"
    assert row.user_id == user.id
    # Stored as a dict in the JSON column...
    assert row.resume_json["summary"] == "Tailored summary."
    # ...and it validates back into a Resume unchanged.
    restored = Resume.model_validate(row.resume_json)
    assert restored.summary == "Tailored summary."
    assert restored.contact.name == "Lee"


def test_list_returns_newest_first(db, user) -> None:
    first = save_resume_version(db, _sample_create("app-1", "first"), user.id)
    second = save_resume_version(db, _sample_create("app-1", "second"), user.id)

    versions = list_resume_versions(db, "app-1", user.id)

    assert [v.id for v in versions] == [second.id, first.id]


def test_list_is_empty_for_application_without_versions(db, user) -> None:
    save_resume_version(db, _sample_create("app-1", "only"), user.id)

    assert list_resume_versions(db, "app-2", user.id) == []


def test_list_only_returns_own_versions(db, user) -> None:
    save_resume_version(db, _sample_create("app-1", "mine"), user.id)
    other = _other_user(db)
    save_resume_version(db, _sample_create("app-1", "theirs"), other.id)

    versions = list_resume_versions(db, "app-1", user.id)

    assert len(versions) == 1
    assert versions[0].resume_json["summary"] == "mine"
