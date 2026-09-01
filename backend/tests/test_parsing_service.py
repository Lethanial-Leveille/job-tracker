"""Tests for the JD parsing service.

The service calls a real, paid, non-deterministic API, so these tests mock the
Anthropic client out entirely — the same instinct as the in-memory DB fixture:
a test must never touch external state. We patch `services.parsing.Anthropic`,
hand back a canned response, and assert the service's own logic: it returns the
parsed object on success and None when the model declines.

The actual API call is verified by hand against a real posting, not here.
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from config import Settings
from schemas.parsing import ParsedJob
from services.parsing import parse_job_description


def _fake_settings() -> Settings:
    # Passing the key explicitly overrides .env, so tests need no real secret.
    return Settings(anthropic_api_key="test-key", anthropic_model="claude-haiku-4-5")


@patch("services.parsing.Anthropic")
def test_returns_parsed_output_on_success(mock_anthropic: MagicMock) -> None:
    expected = ParsedJob(
        type="internship",
        organization="Acme Corp",
        role_or_program="Software Engineering Intern",
        role_family="Software Engineer Intern",
    )
    # client.messages.parse(...).parsed_output -> our canned ParsedJob
    mock_client = MagicMock()
    mock_client.messages.parse.return_value.parsed_output = expected
    mock_anthropic.return_value = mock_client

    result = parse_job_description("some posting text", _fake_settings())

    assert result == expected


@patch("services.parsing.Anthropic")
def test_returns_none_when_model_declines(mock_anthropic: MagicMock) -> None:
    # A refusal or a truncated reply surfaces as parsed_output=None.
    mock_client = MagicMock()
    mock_client.messages.parse.return_value.parsed_output = None
    mock_anthropic.return_value = mock_client

    result = parse_job_description("unparseable garbage", _fake_settings())

    assert result is None


def test_role_family_is_constrained_to_the_canonical_set() -> None:
    """A family outside schemas/roles.py must fail validation, not be stored.

    The database column is a plain VARCHAR, so this Literal is the ONLY thing
    stopping a free-text role family from landing in the data — which would
    silently defeat the whole point of normalizing the field.
    """
    with pytest.raises(ValidationError):
        ParsedJob(
            type="internship",
            organization="Acme Corp",
            role_or_program="Software Engineering Intern",
            role_family="Software Engineering Internship",  # not a canonical value
        )


@patch("services.parsing.Anthropic")
def test_classify_retries_for_titles_the_model_skipped(
    mock_anthropic: MagicMock,
) -> None:
    """A partial answer must be re-asked, not silently accepted.

    Observed live against the real API: 16 titles in, 8 answers back, indices
    0-7, stop_reason "end_turn" at 306 of 2048 tokens. So this is ordinary
    non-determinism rather than truncation, and the only fix is asking again for
    what is missing. Without the retry, half the rows stay unclassified.
    """
    from services.parsing import _ClassifiedRole, _ClassifiedRoles, classify_role_families

    partial = _ClassifiedRoles(
        roles=[_ClassifiedRole(index=0, role_family="Software Engineer Intern")]
    )
    rest = _ClassifiedRoles(
        roles=[_ClassifiedRole(index=1, role_family="Embedded Engineer Intern")]
    )
    mock_client = MagicMock()
    mock_client.messages.parse.side_effect = [
        MagicMock(parsed_output=partial),
        MagicMock(parsed_output=rest),
    ]
    mock_anthropic.return_value = mock_client

    result = classify_role_families(
        ["Software Engineer Intern", "Embedded Software Engineer Intern"],
        _fake_settings(),
    )

    assert result == {
        0: "Software Engineer Intern",
        1: "Embedded Engineer Intern",
    }
    assert mock_client.messages.parse.call_count == 2
    # The second call must ask only about the missing title, by its ORIGINAL
    # index, so the answer maps back without re-numbering.
    second_prompt = mock_client.messages.parse.call_args_list[1].kwargs["messages"][0]["content"]
    assert second_prompt == "1. Embedded Software Engineer Intern"


@patch("services.parsing.Anthropic")
def test_classify_gives_up_after_max_rounds(mock_anthropic: MagicMock) -> None:
    """A title the model never answers for is left out, not guessed at."""
    from services.parsing import _ClassifiedRole, _ClassifiedRoles, classify_role_families

    always_partial = _ClassifiedRoles(
        roles=[_ClassifiedRole(index=0, role_family="Software Engineer Intern")]
    )
    mock_client = MagicMock()
    mock_client.messages.parse.return_value = MagicMock(parsed_output=always_partial)
    mock_anthropic.return_value = mock_client

    result = classify_role_families(["a title", "another title"], _fake_settings())

    assert result == {0: "Software Engineer Intern"}
    assert mock_client.messages.parse.call_count == 3  # max_rounds
