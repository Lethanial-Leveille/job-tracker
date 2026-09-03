"""Tests for Gmail ingestion: matching and staging.

The classifier is mocked out (it is tested in test_email_classify_service.py);
what is exercised here is every DECISION this module makes, because those are
the ones that can be wrong silently.

The cases that matter most:
  - a duplicate delivery costs no model call and creates nothing
  - a message that fails to classify leaves NO row, so it gets redelivered
  - two rows at one company are staged as ambiguous, never guessed between
  - nothing, anywhere, writes to an application's status
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from config import Settings
from models.application import Application, ApplicationStatus, ApplicationType
from models.ingested_email import IngestedEmail
from models.status_suggestion import StatusSuggestion, SuggestionState
from models.user import User
from schemas.email import EmailClassification, IncomingEmail
from services.email_ingest import (
    ingest_message,
    ingest_messages,
    narrow,
    parse_sender,
    received_at_from_ms,
)


def _settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


def _message(message_id: str = "18f2a", **kw) -> IncomingEmail:
    return IncomingEmail(
        message_id=message_id,
        thread_id="t1",
        internal_date_ms=1756915331000,
        from_raw=kw.pop("from_raw", "Neighbor <no-reply@hire.lever.co>"),
        subject=kw.pop("subject", "Thank you for applying to Neighbor"),
        snippet=kw.pop("snippet", "Thank you for submitting your application..."),
    )


def _app(db: Session, user: User, org: str, role: str, status) -> Application:
    row = Application(
        user_id=user.id,
        type=ApplicationType.internship,
        organization=org,
        role_or_program=role,
        posting_url="https://example.com/1",
        status=status,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _classified(**kw) -> EmailClassification:
    return EmailClassification(
        kind=kw.pop("kind", "application_received"),
        organization=kw.pop("organization", "Neighbor"),
        role_hint=kw.pop("role_hint", None),
    )


# --- pure helpers ------------------------------------------------------------


def test_parse_sender_splits_a_display_name_from_the_address() -> None:
    assert parse_sender("Neighbor <no-reply@hire.lever.co>") == (
        "Neighbor",
        "no-reply@hire.lever.co",
    )


def test_parse_sender_handles_a_comma_inside_a_quoted_name() -> None:
    """The case a hand-written regex gets wrong, and the reason this uses
    email.utils.parseaddr instead of splitting on '<'."""
    assert parse_sender('"Smith, Jane" <jane@x.com>') == ("Smith, Jane", "jane@x.com")


def test_parse_sender_handles_a_bare_address() -> None:
    assert parse_sender("careers@example.com") == (None, "careers@example.com")


def test_epoch_ms_converts_to_aware_utc() -> None:
    dt = received_at_from_ms(1756915331000)
    assert dt.tzinfo is not None
    assert dt.year == 2025 or dt.year == 2026  # sanity, not a date assertion


# --- narrowing ---------------------------------------------------------------


def test_a_confirmation_only_applies_to_a_row_not_yet_applied(
    db: Session, user: User
) -> None:
    not_applied = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    already = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.applied)

    survivors = narrow([not_applied, already], "application_received", None)

    assert survivors == [not_applied]


def test_a_rejection_only_applies_to_a_row_already_out(
    db: Session, user: User
) -> None:
    discovered = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    applied = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.applied)

    assert narrow([discovered, applied], "rejection", None) == [applied]


def test_role_hint_breaks_a_tie_between_two_rows_at_one_company(
    db: Session, user: User
) -> None:
    """The Microsoft case. Both rows are eligible, so the hint has to separate
    them."""
    swe = _app(db, user, "Microsoft", "Software Engineer Intern", ApplicationStatus.discovered)
    hw = _app(db, user, "Microsoft", "Hardware Engineer Intern", ApplicationStatus.discovered)

    survivors = narrow([swe, hw], "application_received", "Software Engineering Internship")

    assert survivors == [swe]


def test_a_role_hint_matching_nothing_is_abandoned_not_obeyed(
    db: Session, user: User
) -> None:
    """A title that fits no candidate is weak evidence, not proof of absence.
    Returning nothing here would silently drop a real email."""
    a = _app(db, user, "Microsoft", "Software Engineer Intern", ApplicationStatus.discovered)
    b = _app(db, user, "Microsoft", "Hardware Engineer Intern", ApplicationStatus.discovered)

    survivors = narrow([a, b], "application_received", "Quantitative Researcher")

    assert len(survivors) == 2


def test_an_interview_invite_does_not_propose_a_backwards_step(
    db: Session, user: User
) -> None:
    """A snippet cannot tell a first screen from a third round, so an invite
    arriving when the row is already at phone_screen produces nothing."""
    row = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.phone_screen)

    assert narrow([row], "interview_invite", None) == []


def test_other_never_narrows_to_anything(db: Session, user: User) -> None:
    row = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)

    assert narrow([row], "other", None) == []


# --- end to end --------------------------------------------------------------


@patch("services.email_ingest.classify_email")
def test_one_match_stages_a_suggestion_and_changes_no_status(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    row = _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    mock_classify.return_value = _classified()

    outcome = ingest_message(db, user.id, _message(), _settings())

    assert outcome.result == "suggested"
    suggestion = db.query(StatusSuggestion).one()
    assert suggestion.application_id == row.id
    assert suggestion.suggested_status == ApplicationStatus.applied
    assert suggestion.state == SuggestionState.pending
    # The whole point: the application itself is untouched.
    db.refresh(row)
    assert row.status == ApplicationStatus.discovered


@patch("services.email_ingest.classify_email")
def test_two_matches_stage_candidates_with_no_target(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    a = _app(db, user, "Microsoft", "Software Engineer Intern", ApplicationStatus.discovered)
    b = _app(db, user, "Microsoft", "Data Engineer Intern", ApplicationStatus.discovered)
    mock_classify.return_value = _classified(organization="Microsoft")

    outcome = ingest_message(db, user.id, _message(), _settings())

    assert outcome.result == "ambiguous"
    suggestion = db.query(StatusSuggestion).one()
    # Null target is what makes it impossible for this to flip a status.
    assert suggestion.application_id is None
    assert set(suggestion.candidate_application_ids) == {a.id, b.id}


@patch("services.email_ingest.classify_email")
def test_no_match_is_recorded_as_unmatched(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    mock_classify.return_value = _classified(organization="Nvidia")

    outcome = ingest_message(db, user.id, _message(), _settings())

    assert outcome.result == "unmatched"
    assert db.query(StatusSuggestion).one().application_id is None


@patch("services.email_ingest.classify_email")
def test_a_duplicate_costs_no_model_call(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    mock_classify.return_value = _classified()

    ingest_message(db, user.id, _message("same-id"), _settings())
    assert mock_classify.call_count == 1

    second = ingest_message(db, user.id, _message("same-id"), _settings())

    assert second.result == "duplicate"
    # The pre-check ran before the classifier, so no second call was paid for.
    assert mock_classify.call_count == 1
    assert db.query(IngestedEmail).count() == 1
    assert db.query(StatusSuggestion).count() == 1


@patch("services.email_ingest.classify_email")
def test_a_failed_classification_records_nothing_so_it_is_redelivered(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    """The keystone of the retry design. If a None were recorded, the message
    would be marked permanently handled and lost."""
    mock_classify.return_value = None

    outcome = ingest_message(db, user.id, _message(), _settings())

    assert outcome.result == "not_classified"
    assert db.query(IngestedEmail).count() == 0
    assert db.query(StatusSuggestion).count() == 0


@patch("services.email_ingest.classify_email")
def test_an_unclassifiable_email_is_recorded_so_it_is_not_paid_for_twice(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    """"other" is a successful classification, unlike None. Recording it stops
    the next poll re-billing the same message."""
    mock_classify.return_value = _classified(kind="other", organization=None)

    outcome = ingest_message(db, user.id, _message(), _settings())

    assert outcome.result == "no_action"
    assert db.query(IngestedEmail).count() == 1
    assert db.query(StatusSuggestion).count() == 0


@patch("services.email_ingest.classify_email")
def test_a_repeat_confirmation_does_not_stage_a_second_identical_suggestion(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    """Companies send both "we received it" and a follow-up confirmation. Two
    identical rows to dismiss trains you to dismiss without reading."""
    _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    mock_classify.return_value = _classified()

    ingest_message(db, user.id, _message("first"), _settings())
    outcome = ingest_message(db, user.id, _message("second"), _settings())

    assert outcome.result == "no_action"
    assert db.query(StatusSuggestion).count() == 1


@patch("services.email_ingest.classify_email")
def test_one_bad_message_does_not_abort_the_batch(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    _app(db, user, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    mock_classify.side_effect = [
        _classified(),
        RuntimeError("network blew up"),
        _classified(kind="other", organization=None),
    ]

    outcomes = ingest_messages(
        db,
        user.id,
        [_message("a"), _message("b"), _message("c")],
        _settings(),
    )

    assert [o.result for o in outcomes] == ["suggested", "not_classified", "no_action"]
    # The first message's work survived the second one's failure.
    assert db.query(StatusSuggestion).count() == 1
    assert {e.message_id for e in db.query(IngestedEmail).all()} == {"a", "c"}


@patch("services.email_ingest.classify_email")
def test_ingestion_never_touches_another_users_applications(
    mock_classify: MagicMock, db: Session, user: User
) -> None:
    other = User(email="someone@else.com", password_hash="x")
    db.add(other)
    db.commit()
    theirs = _app(db, other, "Neighbor", "SWE Intern", ApplicationStatus.discovered)
    mock_classify.return_value = _classified()

    outcome = ingest_message(db, user.id, _message(), _settings())

    # Their Neighbor row must be invisible: no match, and no suggestion against it.
    assert outcome.result == "unmatched"
    db.refresh(theirs)
    assert theirs.status == ApplicationStatus.discovered
