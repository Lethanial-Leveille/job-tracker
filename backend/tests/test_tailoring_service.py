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
from services.resume_render import (
    count_lines_containing,
    count_pages,
    count_skill_lines,
    render_html,
    resolve_inline_descriptors,
)
from services.tailoring import (
    cap_bold_spans,
    fit_to_one_page,
    strip_invented_entries,
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
    resume = _resume_with({"experience": 6, "project": 6}, projects=4)
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


# --- Bold-span cap ------------------------------------------------------------
# The prompt asks the model for one bold span per bullet; these prove the code
# guarantees it, because the prompt alone does not (models over-emphasise). Bold
# is the one presentation choice tailoring is allowed to make, so the count is
# the only thing that needs enforcing.


def _bulleted(*bullets: str) -> Resume:
    return Resume(
        contact=Contact(name="Lethanial L. Leveille"),
        projects=[Project(name="Prowl", bullets=list(bullets))],
    )


def test_a_single_bold_span_is_left_alone() -> None:
    r = _bulleted("cut deploys **from 20 minutes to 3** with caching")
    assert cap_bold_spans(r) == []
    assert r.projects[0].bullets[0] == "cut deploys **from 20 minutes to 3** with caching"


def test_extra_bold_spans_are_unwrapped_keeping_the_first() -> None:
    r = _bulleted("**one** then **two** then **three**")
    changed = cap_bold_spans(r)
    assert changed == ["Prowl bullet 1"]
    assert r.projects[0].bullets[0] == "**one** then two then three"


def test_an_unpaired_marker_is_dropped_so_no_asterisks_reach_the_pdf() -> None:
    # The renderer's bold filter only converts matched pairs, so a stray opener
    # would otherwise print as literal asterisks on the resume.
    r = _bulleted("shipped it ** and moved on")
    assert cap_bold_spans(r) == ["Prowl bullet 1"]
    assert "*" not in r.projects[0].bullets[0]


def test_an_empty_span_does_not_consume_the_one_allowed_bold() -> None:
    r = _bulleted("**  ** but the **real result** is here")
    cap_bold_spans(r)
    assert r.projects[0].bullets[0].count("**") == 2
    assert "**real result**" in r.projects[0].bullets[0]


def test_bullets_without_markers_are_untouched() -> None:
    r = _bulleted("plain bullet with no emphasis at all")
    assert cap_bold_spans(r) == []
    assert r.projects[0].bullets[0] == "plain bullet with no emphasis at all"


# --- Never-invent enforcement, whole entries ---------------------------------


def _entry_master() -> Resume:
    return Resume(
        contact=Contact(name="Lee"),
        education=[
            Education(
                institution="University of Florida",
                degree="Bachelor of Science in Computer Engineering",
                dates="Expected May 2028",
                dates_alternate="Expected May 2029",
            )
        ],
        experience=[
            Experience(
                organization="Fuzzy AI",
                role="Software Engineering Intern",
                dates="June 2026 - July 2026",
                bullets=["shipped a thing"],
            )
        ],
        projects=[Project(name="Prowl", bullets=["built a thing"])],
    )


def test_education_copied_into_experience_is_removed() -> None:
    """The real failure: a tailored resume grew an EXPERIENCE entry reading
    "University of Florida / B.S. Computer Engineering / Expected May 2029",
    with the degree filling the required `role` field and no bullets at all."""
    master = _entry_master()
    tailored = master.model_copy(deep=True)
    tailored.experience.append(
        Experience(
            organization="University of Florida",
            role="B.S. Computer Engineering",
            location="Gainesville, FL",
            dates="Expected May 2029",
        )
    )

    removed = strip_invented_entries(master, tailored)

    assert [e.organization for e in tailored.experience] == ["Fuzzy AI"]
    assert any("University of Florida" in r for r in removed)


def test_a_real_experience_entry_survives() -> None:
    master = _entry_master()
    tailored = master.model_copy(deep=True)
    # Bullets are rephrasable by design, so a rewritten one must not look invented.
    tailored.experience[0].bullets = ["shipped a thing, rephrased for this job"]

    removed = strip_invented_entries(master, tailored)

    assert [e.organization for e in tailored.experience] == ["Fuzzy AI"]
    assert removed == []


def test_an_invented_project_is_removed() -> None:
    master = _entry_master()
    tailored = master.model_copy(deep=True)
    tailored.projects.append(Project(name="Kubernetes Scheduler", bullets=["nope"]))

    removed = strip_invented_entries(master, tailored)

    assert [p.name for p in tailored.projects] == ["Prowl"]
    assert any("Kubernetes Scheduler" in r for r in removed)


def test_an_invented_school_is_removed() -> None:
    master = _entry_master()
    tailored = master.model_copy(deep=True)
    tailored.education.append(Education(institution="MIT", degree="B.S. Physics"))

    removed = strip_invented_entries(master, tailored)

    assert [e.institution for e in tailored.education] == ["University of Florida"]
    assert any("MIT" in r for r in removed)


def test_an_entry_that_is_in_the_master_survives_even_if_it_looks_wrong() -> None:
    """The corollary, and the reason this guard cannot be the whole answer: if a
    stray entry was typed into the MASTER, it is real data as far as tailoring is
    concerned and passes through. That fix belongs in the master, not here."""
    master = _entry_master()
    master.experience.append(
        Experience(organization="University of Florida", role="B.S. Computer Engineering")
    )
    tailored = master.model_copy(deep=True)

    removed = strip_invented_entries(master, tailored)

    assert len(tailored.experience) == 2
    assert removed == []


# --- Activities section -------------------------------------------------------


def _activity_resume(n_bullets: int = 1, projects: int = 3) -> Resume:
    r = _resume_with({"Fuzzy AI": 3}, projects=projects)
    r.activities = [
        Experience(
            organization="Prep Academy",
            role="Test Prep Tutor",
            bullets=["tutored students " * 8][:1] * n_bullets,
        )
    ]
    return r


def test_an_activity_is_capped_at_one_bullet_even_when_the_page_fits() -> None:
    """The cap is unconditional, like the coursework trim: a club entry does not
    earn a second line just because there happens to be room for one."""
    r = _activity_resume(n_bullets=3, projects=1)
    fitted, cuts = fit_to_one_page(r)

    assert len(fitted.activities[0].bullets) == 1
    assert any("one bullet" in c for c in cuts)


def test_activities_are_dropped_whole_not_in_part() -> None:
    """A half-printed section reads as a document that ran out of room.

    Every bullet list starts AT the floor of two, so bullet trimming (cut step 1)
    has nothing to take and the loop reaches the activities step with both
    entries still present. That is the case worth pinning: the section goes
    entirely or not at all, never one entry of two.
    """
    r = _resume_with({"experience": 2, "project": 2}, projects=8)
    r.activities = [
        Experience(organization="Prep Academy", role="Tutor", bullets=["x " * 30]),
        Experience(organization="Robotics Club", role="Member", bullets=["y " * 30]),
    ]
    assert count_pages(r) > 1, "fixture must overflow for the cut to be exercised"

    fitted, cuts = fit_to_one_page(r)

    assert fitted.activities == []
    assert any("activities section" in c for c in cuts)


def test_an_invented_activity_is_removed() -> None:
    master = _entry_master()
    master.activities = [Experience(organization="Prep Academy", role="Tutor")]
    tailored = master.model_copy(deep=True)
    tailored.activities.append(Experience(organization="Rotary Club", role="President"))

    removed = strip_invented_entries(master, tailored)

    assert [a.organization for a in tailored.activities] == ["Prep Academy"]
    assert any("Rotary Club" in r for r in removed)


def test_a_descriptor_survives_tailoring_untouched() -> None:
    master = _entry_master()
    master.experience[0].descriptor = "B2B sales automation platform."
    tailored = master.model_copy(deep=True)

    strip_invented_entries(master, tailored)

    assert tailored.experience[0].descriptor == "B2B sales automation platform."


# --- Inline company descriptors ----------------------------------------------
# The descriptor rides on the organization row as a parenthetical when it fits
# there and drops to its own line when it does not. Both paths are pinned,
# because the fallback is the one nobody looks at until a long company name
# silently pushes a resume onto two pages.


def _descriptor_resume(descriptor: str) -> Resume:
    r = _resume_with({"experience": 2, "project": 2}, projects=1)
    r.experience[0].organization = "Fuzzy AI"
    r.experience[0].location = "Singapore"
    r.experience[0].descriptor = descriptor
    return r


def test_a_short_descriptor_rides_inline_on_the_organization_row() -> None:
    r = _descriptor_resume("B2B sales outreach automation platform")

    assert resolve_inline_descriptors(r) == {0}

    html = render_html(r)
    assert '(B2B sales outreach automation platform)' in html
    # And exactly once: the fallback line must not also print it.
    assert html.count("B2B sales outreach automation platform") == 1
    assert 'class="descriptor"' not in html


def test_a_long_descriptor_falls_back_to_its_own_line() -> None:
    # Measured: the row holds about 109 characters of organization plus
    # parenthetical next to a right-aligned "Singapore" before it wraps. This is
    # deliberately just past that, not absurdly long, so the test still fails if
    # the threshold moves.
    long = (
        "Business-to-business sales outreach, contact management and "
        "personalized message generation automation platform"
    )
    r = _descriptor_resume(long)

    assert resolve_inline_descriptors(r) == set()

    html = render_html(r)
    assert 'class="descriptor"' in html
    # Fallback prints it on its own line, never as a parenthetical as well.
    assert f"({long})" not in html
    assert html.count(long) == 1


def test_bold_is_stripped_from_activities_entirely() -> None:
    """Not capped to one span like a job bullet: removed outright.

    The master banks the tutoring bullet with "**3 students**" marked, so this
    is the case that actually occurs rather than a hypothetical one.
    """
    r = Resume(
        contact=Contact(name="Lee"),
        activities=[
            Experience(
                organization="Prep Academy",
                role="Tutor",
                bullets=["Tutoring **3 students** in ACT English and SAT Math."],
            )
        ],
    )

    changed = cap_bold_spans(r)

    assert r.activities[0].bullets[0] == "Tutoring 3 students in ACT English and SAT Math."
    assert any("Prep Academy" in c for c in changed)


def test_an_unbolded_activity_bullet_is_left_alone() -> None:
    r = Resume(
        contact=Contact(name="Lee"),
        activities=[
            Experience(organization="Prep Academy", role="Tutor", bullets=["No bold here."])
        ],
    )

    assert cap_bold_spans(r) == []
    assert r.activities[0].bullets[0] == "No bold here."


# --- Skills rows are one line ------------------------------------------------


def _resume_with_skills(*groups: tuple[str, list[str]]) -> Resume:
    return Resume(
        contact=Contact(name="Lee"),
        skills=[SkillGroup(category=c, items=list(i)) for c, i in groups],
    )


def test_a_wrapping_skills_row_is_trimmed_to_one_line() -> None:
    """The row that shipped two lines: 11 Cloud & DevOps items off the master."""
    r = _resume_with_skills(
        (
            "Cloud & DevOps",
            [
                "PostgreSQL", "MongoDB", "Docker", "Docker Compose",
                "GitHub Actions", "Cloudflare Tunnel", "n8n", "Postman",
                "Git/GitHub", "MQTT", "Kubernetes",
            ],
        )
    )
    assert count_skill_lines(r) == [2]

    fitted, cuts = fit_to_one_page(r)

    assert count_skill_lines(fitted) == [1]
    assert any("dropped skill" in c for c in cuts)


def test_a_long_parenthetical_is_shortened_before_any_item_is_dropped() -> None:
    """One wide entry must not cost the items beside it.

    "AWS (IoT Core, Lambda, DynamoDB, API Gateway)" is as wide as four ordinary
    skills, so trimming its examples is what buys the line back; dropping items
    would spend GitHub Actions to keep AWS service names.
    """
    r = _resume_with_skills(
        (
            "Cloud & DevOps",
            [
                "AWS (IoT Core, Lambda, DynamoDB, API Gateway)",
                "PostgreSQL", "MongoDB", "Docker", "Docker Compose",
                "GitHub Actions",
            ],
        )
    )
    assert count_skill_lines(r) == [2]

    fitted, cuts = fit_to_one_page(r)

    assert count_skill_lines(fitted) == [1]
    assert fitted.skills[0].items[0] == "AWS (IoT Core, Lambda)"
    assert "GitHub Actions" in fitted.skills[0].items
    assert any("shortened" in c for c in cuts)


def test_a_skills_row_that_already_fits_is_left_alone() -> None:
    r = _resume_with_skills(("Languages", ["Python", "C++", "SQL"]))

    fitted, cuts = fit_to_one_page(r)

    assert fitted.skills[0].items == ["Python", "C++", "SQL"]
    assert cuts == []


def test_a_skills_row_is_never_trimmed_to_nothing() -> None:
    """A category with no items reads as broken; a short one just reads short."""
    r = _resume_with_skills(
        ("Cloud & DevOps", ["A" * 90, "B" * 90, "C" * 90, "D" * 90])
    )

    fitted, _ = fit_to_one_page(r)

    assert len(fitted.skills[0].items) >= 3
