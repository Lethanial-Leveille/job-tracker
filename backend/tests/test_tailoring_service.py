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
from services.resume_render import count_lines_containing, count_pages
from services.tailoring import (
    fit_to_one_page,
    strip_invented_skills,
    tailor_resume,
)


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


def test_coursework_is_trimmed_to_a_single_line() -> None:
    """Six real course names wrap to two lines; the tail is dropped until they fit.

    Kept courses stay in their original order, because tailoring returns
    coursework ranked by relevance to the job and dropping from the end is what
    makes the survivors the relevant ones.
    """
    courses = [
        "Data Structures and Algorithms",
        "Software Engineering",
        "Computer Organization",
        "Discrete Structures",
        "Linear Algebra",
        "Digital Logic",
    ]
    resume = _resume_with({"experience": 2, "project": 2}, projects=2)
    resume.education[0].coursework = list(courses)
    assert count_lines_containing(resume, "Coursework") > 1  # the fixture must wrap

    fitted, cuts = fit_to_one_page(resume)

    assert count_lines_containing(fitted, "Coursework") == 1
    kept = fitted.education[0].coursework
    assert kept == courses[: len(kept)], "surviving courses must keep their order"
    assert any("coursework" in c for c in cuts)


def test_coursework_that_already_fits_is_left_alone() -> None:
    resume = _resume_with({"experience": 2, "project": 2}, projects=2)
    resume.education[0].coursework = ["Digital Logic", "Linear Algebra"]

    fitted, cuts = fit_to_one_page(resume)

    assert fitted.education[0].coursework == ["Digital Logic", "Linear Algebra"]
    assert cuts == []


def test_professional_layout_hides_coursework_so_nothing_is_trimmed() -> None:
    """The professional template never renders coursework, so the line count is 0.

    Without the zero case the trim loop would have no wrapped line to shrink and
    could spin, so this pins that it simply does nothing.
    """
    resume = _resume_with({"experience": 2, "project": 2}, projects=2)
    resume.career_stage = "professional"
    resume.education[0].coursework = ["A" * 60] * 8

    fitted, cuts = fit_to_one_page(resume)

    assert count_lines_containing(fitted, "Coursework") == 0
    assert fitted.education[0].coursework == ["A" * 60] * 8
    assert cuts == []


# --- Never-invent enforcement ------------------------------------------------


def _invention_master() -> Resume:
    return Resume(
        contact=Contact(name="Lee"),
        skills=[
            SkillGroup(category="Languages", items=["Python", "C/C++", "JavaScript"]),
            SkillGroup(
                category="Cloud & DevOps",
                items=["AWS (IoT Core, Lambda, DynamoDB, API Gateway)", "Docker"],
            ),
        ],
        projects=[
            Project(name="Prowl", tools=["FastAPI", "PostgreSQL"], bullets=["did a thing"])
        ],
    )


def test_a_skill_from_the_job_description_is_removed() -> None:
    """The real failure: a Mastercard posting listing "Java, Python, C++,
    JavaScript" among its requirements produced a resume claiming Java, which
    appears nowhere in the master."""
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.skills[0].items.insert(0, "Java")

    removed = strip_invented_skills(master, tailored)

    assert "Java" not in tailored.skills[0].items
    assert any("Java" in r for r in removed)


def test_an_invented_skills_category_is_removed_whole() -> None:
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.skills.append(SkillGroup(category="Concepts", items=["Data Structures"]))

    strip_invented_skills(master, tailored)

    assert [g.category for g in tailored.skills] == ["Languages", "Cloud & DevOps"]


def test_shortening_a_parenthetical_list_is_allowed() -> None:
    """The prompt itself tells the model to shorten
    "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" to "AWS (Lambda, DynamoDB)",
    so that is a trim, not an invention, and must survive."""
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.skills[1].items[0] = "AWS (Lambda, DynamoDB)"

    removed = strip_invented_skills(master, tailored)

    assert tailored.skills[1].items[0] == "AWS (Lambda, DynamoDB)"
    assert removed == []


def test_a_new_example_inside_a_parenthetical_is_still_an_invention() -> None:
    """Redshift is not in the master's AWS list, and hiding it inside parentheses
    does not make it true."""
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.skills[1].items[0] = "AWS (Lambda, Redshift)"

    strip_invented_skills(master, tailored)

    assert tailored.skills[1].items == ["Docker"]


def test_a_tool_used_on_a_project_may_be_promoted_into_skills() -> None:
    """PostgreSQL is in the master, on a project rather than in a skills row.
    Surfacing it is a presentation choice, not a false claim."""
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.skills[1].items.append("PostgreSQL")

    removed = strip_invented_skills(master, tailored)

    assert "PostgreSQL" in tailored.skills[1].items
    assert removed == []


def test_a_tool_not_on_that_project_is_removed() -> None:
    master = _invention_master()
    tailored = master.model_copy(deep=True)
    tailored.projects[0].tools.append("Kubernetes")

    strip_invented_skills(master, tailored)

    assert tailored.projects[0].tools == ["FastAPI", "PostgreSQL"]
