"""Tests for the email classification service.

Same instinct as test_parsing_service.py: the service calls a real, paid,
non-deterministic API, so the Anthropic client is mocked out entirely. What is
asserted is the service's OWN logic, never the model's judgement — the prompt's
quality is verified by hand against real mail, not here.

Three things matter and none of them are the verdict itself:
  - an empty message is answered without spending a call
  - a refusal or truncated reply becomes None, so the caller can retry
  - the sender reaches the model as name AND address, since the employer often
    lives in the display name while the domain belongs to the ATS vendor
"""

from unittest.mock import MagicMock, patch

from config import Settings
from schemas.email import EmailClassification
from services.email_classify import classify_email


def _fake_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        anthropic_model="claude-haiku-4-5",
        jwt_secret="test-secret",
    )


def _client(result: EmailClassification | None) -> MagicMock:
    client = MagicMock()
    client.messages.parse.return_value.parsed_output = result
    return client


@patch("services.email_classify.Anthropic")
def test_returns_the_classification_on_success(mock_anthropic: MagicMock) -> None:
    expected = EmailClassification(
        kind="application_received",
        organization="Neighbor",
        role_hint="Software Engineer Intern 2027",
    )
    mock_anthropic.return_value = _client(expected)

    result = classify_email(
        subject="Thank you for applying to Neighbor",
        from_name="Neighbor",
        from_email="no-reply@hire.lever.co",
        snippet="Hello Lethanial, Thank you for submitting your application...",
        settings=_fake_settings(),
    )

    assert result == expected


@patch("services.email_classify.Anthropic")
def test_returns_none_when_the_model_declines(mock_anthropic: MagicMock) -> None:
    """None means "not classified", and the caller must record nothing so the
    next poll redelivers the message. Returning a fabricated "other" here would
    mark it permanently handled."""
    mock_anthropic.return_value = _client(None)

    result = classify_email(
        subject="?",
        from_name=None,
        from_email="x@y.z",
        snippet="...",
        settings=_fake_settings(),
    )

    assert result is None


@patch("services.email_classify.Anthropic")
def test_an_empty_message_costs_no_api_call(mock_anthropic: MagicMock) -> None:
    client = _client(None)
    mock_anthropic.return_value = client

    result = classify_email(
        subject="   ",
        from_name=None,
        from_email="x@y.z",
        snippet=None,
        settings=_fake_settings(),
    )

    assert result is not None
    assert result.kind == "other"
    client.messages.parse.assert_not_called()


@patch("services.email_classify.Anthropic")
def test_sender_name_and_address_both_reach_the_model(
    mock_anthropic: MagicMock,
) -> None:
    """For "Neighbor <no-reply@hire.lever.co>" the employer is in the display
    name and the ATS vendor is in the domain. Dropping either would remove the
    evidence the prompt needs to tell them apart."""
    client = _client(EmailClassification(kind="other"))
    mock_anthropic.return_value = client

    classify_email(
        subject="Your application",
        from_name="Neighbor",
        from_email="no-reply@hire.lever.co",
        snippet="Thank you for applying.",
        settings=_fake_settings(),
    )

    content = client.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert "Neighbor <no-reply@hire.lever.co>" in content
    assert "Your application" in content
    assert "Thank you for applying." in content


@patch("services.email_classify.Anthropic")
def test_a_sender_without_a_display_name_sends_the_bare_address(
    mock_anthropic: MagicMock,
) -> None:
    client = _client(EmailClassification(kind="other"))
    mock_anthropic.return_value = client

    classify_email(
        subject="Update",
        from_name=None,
        from_email="careers@example.com",
        snippet="Hello.",
        settings=_fake_settings(),
    )

    content = client.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert "SENDER: careers@example.com" in content
    assert "<" not in content.split("SENDER:")[1].split("\n")[0]
