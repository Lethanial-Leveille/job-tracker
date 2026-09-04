from models.application import Application, ApplicationStatus, Priority
from models.user import User
from schemas.application import ApplicationCreate, ApplicationUpdate
from services.application import (
    create_application,
    delete_application,
    get_application,
    list_applications,
    update_application,
)


def _make(db, user_id: str, **overrides) -> Application:
    """Create and persist one application owned by user_id, returning the row.

    Pass any field as a keyword to override the default
    (e.g. _make(db, user.id, organization="Google")).
    """
    fields = {
        "type": "internship",
        "organization": "Apple",
        "role_or_program": "SWE Intern",
        "posting_url": "https://example.com",
    }
    fields.update(overrides)
    return create_application(db, ApplicationCreate(**fields), user_id)


def _other_user(db) -> User:
    """A second user, so a test can prove one user cannot see another's rows."""
    row = User(email="other@example.com", password_hash="placeholder-not-a-hash")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_create_application_persists_and_returns_row(db, user):
    data = ApplicationCreate(
        type="internship",
        organization="Apple",
        role_or_program="intern",
        posting_url="https://www.apple.com/",
    )

    result = create_application(db, data, user.id)

    assert result.id is not None
    assert result.organization == "Apple"
    assert result.status == ApplicationStatus.discovered
    assert result.user_id == user.id  # stamped with the owner
    assert db.get(Application, result.id) is not None


def test_create_application_persists_jd_parsed_blob(db, user):
    # An autofilled create carries the parser's extras (no column of their own)
    # in jd_parsed. Confirm the JSON blob survives a round trip to the DB.
    extras = {
        "salary": "$10,000",
        "location": "US or Canada",
        "summary": "A scholarship for CS students.",
        "key_requirements": ["Enrolled undergrad", "CS or related degree"],
    }
    created = _make(db, user.id, jd_parsed=extras)

    fetched = db.get(Application, created.id)

    assert fetched is not None
    assert fetched.jd_parsed == extras


def test_create_application_defaults_jd_parsed_to_none(db, user):
    # A manual create omits jd_parsed entirely; the column should be NULL.
    created = _make(db, user.id)

    assert db.get(Application, created.id).jd_parsed is None


def test_get_application_returns_matching_row(db, user):
    created = _make(db, user.id, organization="Google")

    found = get_application(db, created.id, user.id)

    assert found is not None
    assert found.id == created.id
    assert found.organization == "Google"


def test_get_application_returns_none_for_missing_id(db, user):
    assert get_application(db, "does-not-exist", user.id) is None


def test_get_application_returns_none_for_another_users_row(db, user):
    # The ownership boundary: a row owned by someone else is invisible, so the
    # route will 404 rather than reveal it exists.
    created = _make(db, user.id, organization="Secret Corp")
    other = _other_user(db)

    assert get_application(db, created.id, other.id) is None


def test_list_applications_returns_all_rows(db, user):
    _make(db, user.id, organization="Apple")
    _make(db, user.id, organization="Google")

    results = list_applications(db, user.id)

    assert len(results) == 2
    # order isn't asserted (two rows can share a timestamp); just membership
    assert {r.organization for r in results} == {"Apple", "Google"}


def test_list_applications_only_returns_own_rows(db, user):
    _make(db, user.id, organization="Mine")
    other = _other_user(db)
    _make(db, other.id, organization="Theirs")

    results = list_applications(db, user.id)

    assert {r.organization for r in results} == {"Mine"}


def test_update_application_changes_only_sent_fields(db, user):
    # Known starting point: status defaults to discovered, priority to medium.
    created = _make(db, user.id, organization="Apple", notes="original note")

    # Send ONLY status and priority. Every other field is left unset on the
    # ApplicationUpdate on purpose — that omission is what the test checks.
    changes = ApplicationUpdate(
        status=ApplicationStatus.applied, priority=Priority.high
    )
    updated = update_application(db, changes, created.id, user.id)

    assert updated is not None
    assert updated.status == ApplicationStatus.applied
    assert updated.priority == Priority.high
    # The fields we did NOT send are untouched — the point of a partial update.
    assert updated.organization == "Apple"
    assert updated.notes == "original note"


def test_update_application_returns_none_for_missing_id(db, user):
    changes = ApplicationUpdate(status=ApplicationStatus.applied)
    assert update_application(db, changes, "does-not-exist", user.id) is None


def test_update_application_returns_none_for_another_users_row(db, user):
    created = _make(db, user.id)
    other = _other_user(db)

    changes = ApplicationUpdate(status=ApplicationStatus.applied)
    assert update_application(db, changes, created.id, other.id) is None


def test_delete_application_removes_row(db, user):
    created = _make(db, user.id)

    deleted = delete_application(db, created.id, user.id)

    assert deleted is not None
    assert get_application(db, created.id, user.id) is None


def test_delete_application_returns_none_for_missing_id(db, user):
    assert delete_application(db, "does-not-exist", user.id) is None


def test_delete_application_returns_none_for_another_users_row(db, user):
    created = _make(db, user.id)
    other = _other_user(db)

    assert delete_application(db, created.id, other.id) is None
    # And it still exists for the real owner — the delete didn't go through.
    assert get_application(db, created.id, user.id) is not None


# --- Deleting an application with dependents ----------------------------------
# A saved resume version used to make its application undeletable: the foreign
# key had no ON DELETE rule, Postgres refused the delete, and the route turned
# that into an opaque 500. Since a version is only ever saved for applications
# you actually worked on, the bug hit exactly the rows most worth deleting.


def test_deleting_an_application_takes_its_resume_versions_with_it(db, user) -> None:
    from models.resume_version import ResumeVersion

    app = _make(db, user.id, organization="Palantir Technologies")
    db.add(
        ResumeVersion(
            user_id=user.id,
            application_id=app.id,
            resume_json={"contact": {"name": "Lethanial L. Leveille"}},
            job_description="Build backend services in Python.",
        )
    )
    db.commit()

    assert delete_application(db, app.id, user.id) is not None
    assert db.query(ResumeVersion).filter_by(application_id=app.id).count() == 0


def test_deleting_an_application_keeps_its_status_suggestions(db, user) -> None:
    from datetime import UTC, datetime

    # The opposite rule: an inbound email really arrived, so the suggestion
    # survives with a null link rather than vanishing with its target.
    from models.ingested_email import IngestedEmail
    from models.status_suggestion import StatusSuggestion

    app = _make(db, user.id, organization="Palantir Technologies")
    email = IngestedEmail(
        user_id=user.id,
        message_id="msg-1",
        received_at=datetime.now(UTC).replace(tzinfo=None),
        from_email="recruiting@palantir.com",
    )
    db.add(email)
    db.flush()
    row = StatusSuggestion(
        user_id=user.id,
        application_id=app.id,
        suggested_status="rejected",
        reason="Thanks for applying, we are moving forward with others.",
        source_email_id=email.id,
    )
    db.add(row)
    db.commit()
    suggestion_id = row.id

    assert delete_application(db, app.id, user.id) is not None
    survivor = db.get(StatusSuggestion, suggestion_id)
    assert survivor is not None
    assert survivor.application_id is None
