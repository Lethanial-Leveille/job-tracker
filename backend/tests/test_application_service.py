from schemas.application import ApplicationCreate, ApplicationUpdate
from models.application import Application, ApplicationStatus, Priority
from services.application import (
    create_application,
    get_application,
    list_applications,
    update_application,
    delete_application,
)


def _make(db, **overrides) -> Application:
    """Create and persist one application, returning the saved row.

    Small helper so each test can start from a real row without repeating the
    ApplicationCreate boilerplate. Pass any field as a keyword to override the
    default (e.g. _make(db, organization="Google")).
    """
    fields = {
        "type": "internship",
        "organization": "Apple",
        "role_or_program": "SWE Intern",
        "posting_url": "https://example.com",
    }
    fields.update(overrides)
    return create_application(db, ApplicationCreate(**fields))


def test_create_application_persists_and_returns_row(db):
    # 1. build an ApplicationCreate with only the required fields
    data = ApplicationCreate(type='internship',organization='Apple',role_or_program='intern',posting_url='https://www.apple.com/')


    # 2. call create_application with the db session and that data
    result = create_application(db,data)

    # 3. assert the returned object has an id, the right organization,
    #    and that status defaulted to discovered

    assert result.id is not None
    assert result.organization == 'Apple'
    assert result.status == ApplicationStatus.discovered

    # 4. re-fetch it from the db by id and confirm it's really there
    fetched = db.get(Application, result.id)

    assert fetched is not None


def test_create_application_persists_jd_parsed_blob(db):
    # An autofilled create carries the parser's extras (no column of their own)
    # in jd_parsed. Confirm the JSON blob survives a round trip to the DB.
    extras = {
        "salary": "$10,000",
        "location": "US or Canada",
        "summary": "A scholarship for CS students.",
        "key_requirements": ["Enrolled undergrad", "CS or related degree"],
    }
    created = _make(db, jd_parsed=extras)

    fetched = db.get(Application, created.id)

    assert fetched is not None
    assert fetched.jd_parsed == extras


def test_create_application_defaults_jd_parsed_to_none(db):
    # A manual create omits jd_parsed entirely; the column should be NULL.
    created = _make(db)

    assert db.get(Application, created.id).jd_parsed is None


def test_get_application_returns_matching_row(db):
    created = _make(db, organization="Google")

    found = get_application(db, created.id)

    assert found is not None
    assert found.id == created.id
    assert found.organization == "Google"


def test_get_application_returns_none_for_missing_id(db):
    assert get_application(db, "does-not-exist") is None


def test_list_applications_returns_all_rows(db):
    _make(db, organization="Apple")
    _make(db, organization="Google")

    results = list_applications(db)

    assert len(results) == 2
    # order isn't asserted (two rows can share a timestamp); just membership
    assert {r.organization for r in results} == {"Apple", "Google"}


def test_update_application_changes_only_sent_fields(db):
    # Known starting point: status defaults to discovered, priority to medium.
    created = _make(db, organization="Apple", notes="original note")

    # Send ONLY status and priority. Every other field is left unset on the
    # ApplicationUpdate on purpose — that omission is what the test checks.
    changes = ApplicationUpdate(
        status=ApplicationStatus.applied, priority=Priority.high
    )
    updated = update_application(db, changes, created.id)

    assert updated is not None
    # The two fields we sent did change:
    assert updated.status == ApplicationStatus.applied
    assert updated.priority == Priority.high
    # The fields we did NOT send are untouched — this is the whole point of a
    # partial update, and what exclude_unset protects:
    assert updated.organization == "Apple"
    assert updated.notes == "original note"


def test_update_application_returns_none_for_missing_id(db):
    changes = ApplicationUpdate(status=ApplicationStatus.applied)
    assert update_application(db, changes, "does-not-exist") is None


def test_delete_application_removes_row(db):
    created = _make(db)

    deleted = delete_application(db, created.id)

    assert deleted is not None
    # And it's really gone from the database:
    assert get_application(db, created.id) is None


def test_delete_application_returns_none_for_missing_id(db):
    assert delete_application(db, "does-not-exist") is None
