"""Tests for the JD parsing service.

The service calls a real, paid, non-deterministic API, so these tests mock the
Anthropic client out entirely — the same instinct as the in-memory DB fixture:
a test must never touch external state. We patch `services.parsing.Anthropic`,
hand back a canned response, and assert the service's own logic: it returns the
parsed object on success and None when the model declines.

The actual API call is verified by hand against a real posting, not here.
"""

from unittest.mock import MagicMock, patch

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
