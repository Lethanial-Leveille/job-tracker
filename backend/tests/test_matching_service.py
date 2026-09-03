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


def test_no_requirements_is_an_empty_report_not_a_failure() -> None:
    # No client is patched: an empty list must not reach the API at all.
    report = assess_requirements(_master(), [], _fake_settings())

    assert report is not None
    assert report.total == 0
    assert report.met_count == 0
