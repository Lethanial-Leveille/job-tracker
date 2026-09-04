"""Tests for the requirement matching service.

Same instinct as test_parsing_service.py: the service calls a real, paid,
non-deterministic API, so the Anthropic client is mocked out entirely and what
is asserted is the service's OWN logic — the parts that would silently produce a
wrong number if they broke.

Three things matter here and none of them are the model's judgement:
  - counts are computed from the verdict list, never taken from the model
  - a requirement the model skips becomes "unknown", not a dropped row
  - the retry re-asks only for what is still missing, by original index
"""

from datetime import date
from unittest.mock import MagicMock, patch

from config import Settings
from schemas.fit import RequirementVerdict, RequirementVerdicts
from schemas.resume import Contact, Resume
from services.matching import assess_requirements


def _fake_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        anthropic_model="claude-haiku-4-5",
        jwt_secret="test-secret",
    )


def _master() -> Resume:
    return Resume(
        contact=Contact(name="Lee Leveille"),
        education=[],
        skills=[],
        experience=[],
        projects=[],
    )


def _reply(*verdicts: RequirementVerdict) -> MagicMock:
    client = MagicMock()
    client.messages.parse.return_value.parsed_output = RequirementVerdicts(
        verdicts=list(verdicts)
    )
    return client


@patch("services.matching.Anthropic")
def test_counts_are_computed_not_taken_from_the_model(
    mock_anthropic: MagicMock,
) -> None:
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=0, verdict="met", evidence="Built X"),
        RequirementVerdict(index=1, verdict="partial", evidence="Adjacent Y"),
        RequirementVerdict(index=2, verdict="missing"),
    )

    report = assess_requirements(
        _master(), ["Python", "Kubernetes", "5 years experience"], _fake_settings()
    )

    assert report is not None
    assert report.met_count == 1
    assert report.partial_count == 1
    assert report.total == 3


@patch("services.matching.Anthropic")
def test_requirements_are_paired_back_to_their_own_text(
    mock_anthropic: MagicMock,
) -> None:
    # Answers deliberately out of order: the index, not the position, decides
    # which requirement each verdict belongs to.
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=1, verdict="met", evidence="Used Kubernetes"),
        RequirementVerdict(index=0, verdict="missing"),
    )

    report = assess_requirements(_master(), ["Python", "Kubernetes"], _fake_settings())

    assert report is not None
    assert report.matches[0].requirement == "Python"
    assert report.matches[0].verdict == "missing"
    assert report.matches[1].requirement == "Kubernetes"
    assert report.matches[1].verdict == "met"


@patch("services.matching.Anthropic")
def test_unanswered_requirement_becomes_unknown_and_still_counts(
    mock_anthropic: MagicMock,
) -> None:
    """The important one. A model that answers 2 of 3 and stops must not shrink
    the denominator — that would turn "1 of 3 met" into "1 of 2 met" and quietly
    flatter the resume."""
    # Same partial reply on every round, so the retry cannot fill the gap.
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=0, verdict="met", evidence="Built X"),
        RequirementVerdict(index=1, verdict="missing"),
    )

    report = assess_requirements(
        _master(), ["Python", "Kubernetes", "Rust"], _fake_settings()
    )

    assert report is not None
    assert report.total == 3
    assert report.matches[2].verdict == "unknown"
    assert report.matches[2].requirement == "Rust"
    assert report.met_count == 1


@patch("services.matching.Anthropic")
def test_retry_asks_only_for_the_missing_indices(mock_anthropic: MagicMock) -> None:
    client = MagicMock()
    # First round answers only index 0; second round supplies index 1.
    client.messages.parse.side_effect = [
        MagicMock(
            parsed_output=RequirementVerdicts(
                verdicts=[RequirementVerdict(index=0, verdict="met", evidence="X")]
            )
        ),
        MagicMock(
            parsed_output=RequirementVerdicts(
                verdicts=[RequirementVerdict(index=1, verdict="missing")]
            )
        ),
    ]
    mock_anthropic.return_value = client

    report = assess_requirements(_master(), ["Python", "Rust"], _fake_settings())

    assert report is not None
    assert report.total == 2
    assert report.matches[1].verdict == "missing"

    # The second prompt must mention only the still-missing requirement, still
    # numbered 1 — its ORIGINAL index, not renumbered to 0.
    second_prompt = client.messages.parse.call_args_list[1].kwargs["messages"][0][
        "content"
    ]
    assert "1. Rust" in second_prompt
    assert "0. Python" not in second_prompt


@patch("services.matching.Anthropic")
def test_returns_none_when_model_declines(mock_anthropic: MagicMock) -> None:
    client = MagicMock()
    client.messages.parse.return_value.parsed_output = None
    mock_anthropic.return_value = client

    assert assess_requirements(_master(), ["Python"], _fake_settings()) is None


@patch("services.matching.Anthropic")
def test_unstated_is_counted_separately_from_missing(
    mock_anthropic: MagicMock,
) -> None:
    """The distinction that made the first live run wrong.

    "Right to work without visa sponsorship" is not a skill the resume failed to
    show — it is a fact no resume normally states. Counting it as "missing" told
    Lee he did not meet a requirement he does meet. It gets its own count so the
    headline can leave it out of the denominator.
    """
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=0, verdict="met", evidence="Enrolled at UF"),
        RequirementVerdict(
            index=1, verdict="unstated", evidence="Confirm your work authorization"
        ),
    )

    report = assess_requirements(
        _master(),
        ["Currently enrolled in a Bachelor's program", "Right to work without sponsorship"],
        _fake_settings(),
    )

    assert report is not None
    assert report.met_count == 1
    assert report.unstated_count == 1
    # Still in `total`; the UI subtracts unstated to get the denominator.
    assert report.total == 2


@patch("services.matching.Anthropic")
def test_todays_date_is_supplied_for_timing_requirements(
    mock_anthropic: MagicMock,
) -> None:
    """"Must be returning to studies afterwards" cannot be judged from a
    graduation date alone — there is nothing to compare it against, and the
    model has no reliable clock. The date is passed in rather than assumed."""
    client = _reply(RequirementVerdict(index=0, verdict="met", evidence="Grad 2029"))
    mock_anthropic.return_value = client

    assess_requirements(
        _master(), ["Must be returning to studies after the internship"], _fake_settings()
    )

    prompt = client.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert "TODAY'S DATE:" in prompt
    assert date.today().isoformat() in prompt


def test_no_requirements_is_an_empty_report_not_a_failure() -> None:
    # No client is patched: an empty list must not reach the API at all.
    report = assess_requirements(_master(), [], _fake_settings())

    assert report is not None
    assert report.total == 0
    assert report.met_count == 0


def test_a_report_stored_before_unstated_existed_still_reads() -> None:
    """Regression: FitReport validates the stored `fit_report` JSON column, not
    just fresh API responses, so a field added without a default breaks every
    report already in the database — and because one bad row fails
    `list[ApplicationRead]`, it takes the entire applications list down with it.

    Any field added to FitReport from now on needs a default for the same reason.
    """
    from schemas.fit import FitReport

    legacy = {
        "matches": [
            {"requirement": "Python", "verdict": "met", "evidence": "Built X"}
        ],
        "met_count": 3,
        "partial_count": 0,
        "total": 5,
        "computed_at": "2026-09-03T16:00:00",
    }

    report = FitReport.model_validate(legacy)

    assert report.unstated_count == 0
    assert report.met_count == 3


@patch("services.matching.Anthropic")
def test_preferred_items_are_counted_apart_from_required(
    mock_anthropic: MagicMock,
) -> None:
    """The headline must stay on the hard requirements.

    Folding preferences into the same total turns "2 of 2 required met" into
    "2 of 4", which reads as a weak fit for someone who clears every gate. The
    preferred list is reported as its own line instead.
    """
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=0, verdict="met", evidence="Enrolled"),
        RequirementVerdict(index=1, verdict="met", evidence="C++ in M.I.L.E.S."),
        RequirementVerdict(index=2, verdict="met", evidence="Python throughout"),
        RequirementVerdict(index=3, verdict="missing"),
    )

    report = assess_requirements(
        _master(),
        ["Pursuing a Bachelor's degree", "Proficiency in C++"],
        _fake_settings(),
        preferred=["Proficiency in Python", "Hardware-in-the-Loop experience"],
    )

    assert report is not None
    assert report.met_count == 2
    assert report.total == 2
    assert report.preferred_met_count == 1
    assert report.preferred_total == 2
    # Every item is still present and labelled, in the order given.
    assert [m.kind for m in report.matches] == [
        "required",
        "required",
        "preferred",
        "preferred",
    ]


@patch("services.matching.Anthropic")
def test_a_posting_with_only_preferred_items_still_assesses(
    mock_anthropic: MagicMock,
) -> None:
    mock_anthropic.return_value = _reply(
        RequirementVerdict(index=0, verdict="met", evidence="Python throughout"),
    )

    report = assess_requirements(
        _master(), [], _fake_settings(), preferred=["Proficiency in Python"]
    )

    assert report is not None
    assert report.total == 0
    assert report.preferred_met_count == 1


# --- Stale fit-report invalidation --------------------------------------------
# A fit report is a cache computed against the master resume as it stood at the
# time. Editing the master invalidates every stored report, and a stale one
# looks exactly like a fresh one in the UI, so failing to clear is worse than
# never having run the sync.

from datetime import UTC, datetime, timedelta  # noqa: E402

from models.application import Application  # noqa: E402
from schemas.application import ApplicationCreate  # noqa: E402
from services.application import create_application  # noqa: E402
from services.matching import clear_stale_fit_reports  # noqa: E402


def _app_with_report(db, user_id: str, computed_at, org="Apple") -> Application:
    app = create_application(
        db,
        ApplicationCreate(
            type="internship",
            organization=org,
            role_or_program="SWE Intern",
            posting_url=f"https://example.com/{org}",
        ),
        user_id,
    )
    app.fit_report = {"verdicts": []}
    app.fit_computed_at = computed_at
    db.commit()
    return app


def test_a_report_older_than_the_master_edit_is_cleared(db, user) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    app = _app_with_report(db, user.id, now - timedelta(hours=2))
    assert clear_stale_fit_reports(db, user.id, now) == 1
    db.refresh(app)
    assert app.fit_report is None
    assert app.fit_computed_at is None


def test_a_report_newer_than_the_master_edit_is_kept(db, user) -> None:
    # Re-running the sync must not throw away work done since the edit.
    now = datetime.now(UTC).replace(tzinfo=None)
    app = _app_with_report(db, user.id, now + timedelta(hours=1))
    assert clear_stale_fit_reports(db, user.id, now) == 0
    db.refresh(app)
    assert app.fit_report is not None


def test_a_report_with_no_timestamp_is_treated_as_stale(db, user) -> None:
    # Rows predate fit_computed_at; unknown age means it cannot be trusted.
    now = datetime.now(UTC).replace(tzinfo=None)
    app = _app_with_report(db, user.id, None)
    assert clear_stale_fit_reports(db, user.id, now) == 1
    db.refresh(app)
    assert app.fit_report is None


def test_another_user_s_reports_are_untouched(db, user) -> None:
    from models.user import User

    other = User(email="other@example.com", password_hash="placeholder-not-a-hash")
    db.add(other)
    db.commit()
    now = datetime.now(UTC).replace(tzinfo=None)
    theirs = _app_with_report(db, other.id, now - timedelta(hours=2), org="Other")
    assert clear_stale_fit_reports(db, user.id, now) == 0
    db.refresh(theirs)
    assert theirs.fit_report is not None
