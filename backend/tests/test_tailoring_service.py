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
from schemas.resume import (
    Contact,
    Education,
    Experience,
    Project,
    Resume,
    SkillGroup,
)
from services.resume_render import count_pages
from services.tailoring import fit_to_one_page, tailor_resume


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


# --- One-page fit ------------------------------------------------------------
# These render for real through WeasyPrint. That is deliberate: the whole point
# of the loop is that only a real layout knows the page count, so a test with a
# mocked renderer would prove nothing. No network or database is involved.


def _resume_with(bullet_counts: dict[str, int], projects: int = 3) -> Resume:
    """A resume whose size is controlled by bullet counts, for fit testing.

    Deliberately shaped like a real one — skills rows, and a tools and links line
    per project — because that per-entry overhead is most of what fills the page.
    An early version of this fixture was bare bullets and 25 of them still fit on
    one page, which made the overflow tests vacuous.
    """
    bullet = (
        "Built a serverless cloud pipeline streaming classified readings to a "
        "Dockerized React dashboard with live charts and alerting"
    )
    return Resume(
        contact=Contact(name="Lee", location="Hollywood, FL", email="l@example.com"),
        education=[
            Education(
                institution="University of Florida",
                degree="BS Computer Engineering",
                gpa="3.77 / 4.00",
                coursework=["Data Structures", "Digital Logic", "Computer Organization"],
            )
        ],
        skills=[
            SkillGroup(category=f"Group {i}", items=["Python", "C", "TypeScript", "SQL"])
            for i in range(4)
        ],
        experience=[
            Experience(
                organization="Fuzzy AI",
                role="SWE Intern",
                bullets=[bullet] * bullet_counts.get("experience", 3),
            )
        ],
        projects=[
            Project(
                name=f"Project {i}",
                tools=["Python", "FastAPI", "React", "Docker", "AWS"],
                links=[f"github.com/lee/project-{i}"],
                bullets=[bullet] * bullet_counts.get("project", 3),
            )
            for i in range(projects)
        ],
    )


def test_a_resume_that_already_fits_is_returned_untouched() -> None:
    resume = _resume_with({"experience": 2, "project": 2}, projects=2)
    fitted, cuts = fit_to_one_page(resume)

    assert cuts == []
    assert count_pages(fitted) == 1
    assert fitted == resume


def test_an_overflowing_resume_is_trimmed_to_one_page() -> None:
    resume = _resume_with({"experience": 5, "project": 5}, projects=4)
    assert count_pages(resume) > 1  # the fixture must actually overflow

    fitted, cuts = fit_to_one_page(resume)

    assert count_pages(fitted) == 1
    assert cuts, "a trimmed resume must report what it cut"


def test_trimming_takes_the_last_bullet_of_the_longest_entry_first() -> None:
    """Bullets arrive in relevance order, so the last of the longest list is the
    least relevant line on the page — and a project loses before a job does."""
    resume = _resume_with({"experience": 3, "project": 7}, projects=4)
    assert count_pages(resume) > 1  # the fixture must actually overflow

    _, cuts = fit_to_one_page(resume)

    assert cuts[0] == "dropped the last bullet from Project 0"


def test_trimming_stops_rather_than_gutting_the_resume() -> None:
    """An unfittable resume comes back long, not reduced to a stub.

    Every entry is already at the two-bullet floor and there are only two
    projects, so there is nothing left to cut cheaply. Returning it over-length
    lets the caller see the problem; silently stripping it to one page would
    hide it.
    """
    long_bullet = " ".join(["word"] * 220)
    resume = Resume(
        contact=Contact(name="Lee"),
        experience=[
            Experience(organization="Fuzzy AI", role="SWE Intern", bullets=[long_bullet] * 2)
        ],
        projects=[Project(name=f"P{i}", bullets=[long_bullet] * 2) for i in range(2)],
    )

    fitted, _ = fit_to_one_page(resume)

    assert count_pages(fitted) > 1
    assert len(fitted.projects) == 2
    assert all(len(p.bullets) == 2 for p in fitted.projects)
    assert len(fitted.experience[0].bullets) == 2
