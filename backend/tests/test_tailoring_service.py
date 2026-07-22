"""Tests for the resume tailoring service.

Same instinct as the parser's tests: `tailor_resume` calls a real, paid,
non-deterministic API (Opus this time), so we mock the Anthropic client out
entirely and assert only the service's own logic — it returns the tailored
Resume on success and None when the model declines or is truncated. We patch
`services.tailoring.Anthropic`, hand back a canned parsed_output, and never
touch the network.

The real tailoring quality is verified by hand against a live job description,
not here — a mock can't judge whether the bullets are good, only that the
plumbing returns what the SDK gives it.
"""

from unittest.mock import MagicMock, patch

from config import Settings
from schemas.resume import Contact, Resume
from services.tailoring import tailor_resume


def _fake_settings() -> Settings:
    # Passing the key explicitly overrides .env, so tests need no real secret.
    return Settings(
        anthropic_api_key="test-key", anthropic_tailoring_model="claude-opus-4-8"
    )


def _fake_master() -> Resume:
    # The master is only forwarded to the (mocked) client, never inspected by the
    # service, so a minimal valid Resume is enough — name is the one required field.
    return Resume(contact=Contact(name="Lee"))


@patch("services.tailoring.Anthropic")
def test_returns_tailored_resume_on_success(mock_anthropic: MagicMock) -> None:
    expected = Resume(contact=Contact(name="Lee"), summary="Tailored for this job.")
    # client.messages.parse(...).parsed_output -> our canned Resume
    mock_client = MagicMock()
    mock_client.messages.parse.return_value.parsed_output = expected
    mock_anthropic.return_value = mock_client

    result = tailor_resume(_fake_master(), "some job description", _fake_settings())

    assert result == expected


@patch("services.tailoring.Anthropic")
def test_returns_none_when_model_declines(mock_anthropic: MagicMock) -> None:
    # A refusal or a truncated reply surfaces as parsed_output=None.
    mock_client = MagicMock()
    mock_client.messages.parse.return_value.parsed_output = None
    mock_anthropic.return_value = mock_client

    result = tailor_resume(_fake_master(), "some job description", _fake_settings())

    assert result is None
