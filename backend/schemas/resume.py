"""The resume schema: one shape shared by three consumers.

This is the structural heart of resume tailoring, and the clearest expression
of the project's one big idea (vision.md): separate content from format. The
same `Resume` model is used in three places, and getting it right makes all
three "just work":

1. Your MASTER file (`backend/data/master_resume.yaml`) is written in this shape.
   It is the single source of truth for your resume content.
2. TAILORING reads a `Resume` (your master) plus a job description and writes
   back a `Resume` in the *same* shape — reordered, trimmed, rephrased for that
   job. Same schema in and out (vision's rule), so nothing downstream changes.
3. The RENDERER reads a `Resume` and lays out the PDF. It never sees the model;
   it only reads these fields.

Two design choices worth calling out, because they're the non-obvious ones:

- The master is a SUPERSET / a "bank." You keep all 5 projects and every bullet
  here; tailoring's job is to *select* a subset of projects and the strongest
  bullets for a given job. Nothing is invented — tailoring only ever chooses,
  reorders, and rephrases what's already in the master (hard rule #2).
- Dates are plain strings, NOT `date` objects. A resume shows "Expected May
  2029", "April 2025 - Present", "Summer 2025" — freeform text a real `date`
  type would reject. This is the deliberate opposite of the database's
  `deadline` column, which is a real typed date because you sort by it. Here you
  never sort; you only display.

Fields stay PLAIN-TYPED (no `Field(min_length=...)` / number constraints) on
purpose: tailoring will hand this model to Claude via structured outputs, and
structured outputs rejects length/number constraints — the same caveat that
shaped `ParsedJob` (see docs/decisions.md, v2 JD parsing). Required fields (no
default) are the fixed identity facts tailoring must never drop or fabricate;
optional fields default to None or an empty list so a partial resume still
validates.
"""

from typing import Literal

from pydantic import BaseModel


class Contact(BaseModel):
    """Fixed identity facts. Tailoring never touches any of this.

    Most of these render into the PDF header. `work_authorization` does NOT —
    templates/resume.html names the fields it prints (location, phone, email,
    and the link line), so a field absent from that list is stored and never
    shown. It lives here because it is an identity fact like the rest, and being
    inside Contact means the tailoring prompt's "never change identity facts"
    rule already protects it for free.

    It exists because postings routinely require it ("must have the right to
    work without visa sponsorship") and a resume otherwise has NO way to answer
    that. Judging such a requirement against a resume that structurally cannot
    state it returns "missing" for every candidate forever, which is not
    strictness, just the wrong document.
    """

    name: str
    location: str | None = None
    phone: str | None = None
    email: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    # Free text, e.g. "US citizen, no sponsorship required". Never rendered.
    work_authorization: str | None = None


class Education(BaseModel):
    """A school. `coursework` is tailorable (surface courses relevant to a job);
    the rest (institution, degree, gpa) is fixed fact.

    `dates_alternate` exists because a student can have two graduation dates that
    are BOTH true. Lee has 94 credit hours against a 128-credit degree, so he can
    finish in 2028 or take the extra year to 2029, and which one he leads with
    depends on the posting: some programs only accept underclassmen. Holding both
    here (rather than keeping a second copy of the whole resume) means the two
    dates cannot drift apart, and the rest of the resume is shared by
    construction. Which one PRINTS is `Resume.grad_date_variant`.
    """

    institution: str
    degree: str
    location: str | None = None
    dates: str | None = None          # freeform, e.g. "Expected May 2029"
    # Optional second graduation date. None (the default) means this school has
    # only one, and `grad_date_variant` then has nothing to switch to.
    dates_alternate: str | None = None
    gpa: str | None = None            # e.g. "3.73 / 4.00"
    # Pydantic copies list defaults per-instance, so the usual mutable-default
    # trap (every instance sharing one list) does not apply here.
    honors: list[str] = []            # e.g. ["Dean's List"]
    coursework: list[str] = []        # tailorable: select the relevant courses


class SkillGroup(BaseModel):
    """One labeled row of skills, e.g. category "Languages", items [Python, C]."""

    category: str
    items: list[str] = []
    # Which flavour this row leads on. Promotion only — never exclusion, unlike
    # Project.tracks.
    #
    # The asymmetry is the point. Dropping a project the reader does not care
    # about buys space on a one-page resume; dropping a skills row just hides
    # things you can do. So an embedded resume still lists the web stack, it
    # simply does not lead with it.
    tracks: list[Literal["swe", "embedded"]] = []


class Experience(BaseModel):
    """A job. `bullets` is a bank: hold every bullet here, let tailoring keep the
    strongest ~4 and rephrase them for the target job.

    Also the shape used for `Resume.activities` (leadership, clubs, tutoring),
    which needs exactly these fields. Reusing the model rather than declaring a
    near-identical `Activity` keeps one set of rules: the never-invent entry
    guard, the tailoring prompt's "identity facts are fixed", and the renderer's
    two-column header row all apply to both without being written twice.
    """

    organization: str
    role: str
    location: str | None = None
    dates: str | None = None
    # One short line naming what the employer actually DOES, printed under the
    # role. A reader who has never heard of the company cannot judge the bullets
    # without it, and the bullets themselves should not spend words explaining
    # the product. Optional because a self-explanatory organization does not need
    # one, and because stored resumes predate the field (see the module docstring
    # on defaults).
    descriptor: str | None = None
    bullets: list[str] = []


class Project(BaseModel):
    """A project. The master holds ALL of them; tailoring selects a subset of
    projects (and, within each, a subset of bullets). `links` is a list because
    one project can have several repos (M.I.L.E.S. has two)."""

    name: str
    tools: list[str] = []
    links: list[str] = []
    dates: str | None = None
    # Which resume flavours this belongs on. EMPTY means every one, which is
    # the right default: most projects are worth showing whoever is reading.
    #
    # A tag does two things at once, and that is deliberate rather than
    # economical. On the resume you are building it LEADS, because tagging a
    # project for a track is a statement that it is the one to open with. On
    # every other track it is EXCLUDED, because the same statement says it is
    # specific to that audience.
    #
    # Two tags reproduce both hand-built base resumes exactly: FormFactor is
    # tagged embedded, Prowl is tagged swe, everything else is untagged and
    # simply follows in order. A rule derived from the tools instead would have
    # got it wrong — the embedded resume keeps MILES second despite it carrying
    # no embedded work at all, because it is the strongest project regardless.
    tracks: list[Literal["swe", "embedded"]] = []
    bullets: list[str] = []


# --- What tailoring is allowed to AUTHOR ---------------------------------------
# Four narrowed copies of the models above, holding only the fields the model may
# write. Everything omitted is an identity fact that tailor_resume() restores
# from the master straight after the call, so asking the model for it bought
# nothing and cost twice.
#
# The first cost is correctness. The prompt forbids changing identity facts and
# the model does it anyway: on 2026-09-09 a tailored resume came back with the
# two graduation dates SWAPPED, which silently inverts the grad-date switch.
# A field the schema does not contain cannot come back wrong.
#
# The second cost is the grammar. Structured outputs compile this schema into a
# grammar with a hard size ceiling, and on 2026-09-22 adding `track`/`tracks`
# pushed it over: every tailoring call failed with "The compiled grammar is too
# large" until these models existed. Measured against the live API, dropping any
# TWO of these fields clears the ceiling; dropping all of them leaves headroom.
#
# So the rule for a new field is the same rule twice over: if tailoring does not
# have to write it, it belongs on the full model above and NOT here.


class TailoredEducation(BaseModel):
    """A school, as tailoring may write it: the name, and the courses it chose.

    `institution` is not content, it is the join key — tailor_resume() looks the
    school up by it and rebuilds the entry from the master. `coursework` is the
    one genuinely tailorable part, selecting courses relevant to the posting.
    """

    institution: str
    coursework: list[str] = []


class TailoredSkillGroup(BaseModel):
    """A skills row, minus `tracks` (which flavour the row leads on — a property
    of the row, not of this job)."""

    category: str
    items: list[str] = []


class TailoredExperience(BaseModel):
    """A job, minus `descriptor` (a fixed fact about the employer, restored by
    organization name)."""

    organization: str
    role: str
    location: str | None = None
    dates: str | None = None
    bullets: list[str] = []


class TailoredProject(BaseModel):
    """A project, minus `links` and `tracks` — both fixed facts about the
    project, restored by project name."""

    name: str
    tools: list[str] = []
    dates: str | None = None
    bullets: list[str] = []


class TailoredResume(BaseModel):
    """Everything tailoring is allowed to produce: a Resume minus `activities`.

    This is the shape handed to Claude as a structured-output schema, and the
    split exists for two reasons that happen to agree.

    The domain reason: activities are not tailorable. They are selected
    positionally (one bullet each) and dropped as a whole section when the page
    is tight, so there is nothing for the model to choose. Like `career_stage`
    and `descriptor`, they are restored from the master afterwards.

    The hard reason: structured outputs compile the schema into a grammar, and
    adding `activities` pushed it over the API's size limit — every tailoring
    call failed with "The compiled grammar is too large" until this split. Adding
    another list-of-objects field to THIS model risks the same failure, so a new
    field belongs on Resume below unless the model genuinely has to write it.
    """

    # Rendering ARRANGEMENT, not content: "student" puts education first with GPA
    # and coursework shown; "professional" leads with experience and hides GPA/
    # coursework (degree + school only). The renderer (templates/resume.html)
    # reads this to choose the section order. Defaults to "student" so any resume
    # saved before this field existed keeps its original layout. Tailoring must
    # never change it — it's a fixed setting like the contact block, and the
    # tailoring service forces it back from the master to guarantee that.
    career_stage: Literal["student", "professional"] = "student"
    # Which resume you are handing out: the general software one, or the
    # embedded one. A rendering SETTING like career_stage and grad_date_variant,
    # never chosen by tailoring, which forces it back from the master.
    #
    # This is what the builder now offers instead of student versus
    # professional. The two arrangements still exist and career_stage still
    # picks them; there is simply no longer a second person using the
    # professional one, and the choice that matters every day is which flavour
    # of the same student resume goes out.
    #
    # It selects CONTENT, not section order: which projects appear and which
    # skills lead. See services/resume.py select_for_track.
    track: Literal["swe", "embedded"] = "swe"
    # Which graduation date prints, when an Education carries two (see
    # Education.dates_alternate). "primary" prints `dates`; "alternate" prints
    # `dates_alternate`, falling back to `dates` for any school that has no
    # alternate. Like career_stage this is a fixed SETTING, not content: tailoring
    # must never choose it, and tailor_resume() forces it back from the master.
    # Defaults to "primary" so a resume saved before this field existed is
    # unaffected.
    grad_date_variant: Literal["primary", "alternate"] = "primary"
    contact: Contact
    summary: str | None = None        # the one free-text spot tailoring may rewrite
    # The narrowed models above, not the full ones: see their header comment.
    education: list[TailoredEducation] = []
    skills: list[TailoredSkillGroup] = []
    experience: list[TailoredExperience] = []
    projects: list[TailoredProject] = []   # the full bank; tailoring keeps a subset


class Resume(TailoredResume):
    """A complete resume: everything tailoring writes, plus the parts it cannot.

    Section order here is the order the renderer prints. What tailoring MAY
    change: rewrite `summary`; reorder/select `projects` and `experience`
    entries; select/reorder/rephrase `bullets`, including where each one places
    its single **bold** span; select `coursework` and reorder `skills`. What it
    may NOT change: any name, org, role, date, degree, gpa, or project name — and
    it may never add a bullet, skill, or number that isn't already in the master
    (hard rule #2, never invent).
    """

    # Widen the four narrowed fields back to the full models. A Resume is what
    # the renderer, the master and the stored versions all use, so it carries
    # every field; TailoredResume is only ever the shape handed to the model.
    education: list[Education] = []
    skills: list[SkillGroup] = []
    experience: list[Experience] = []
    projects: list[Project] = []

    # Leadership, clubs, tutoring. Same shape as `experience` and printed last,
    # under its own heading. It is the LOWEST-VALUE section on the page, so the
    # one-page trim drops it whole rather than printing a partial entry: half an
    # activities section reads as a document that ran out of room, which is worse
    # than not having the section at all.
    activities: list[Experience] = []


# Route input wrapper, NOT part of the three-consumer Resume shape above. This is
# the body of POST /resume/tailor: the job description text to tailor against.
# Mirrors ParseRequest — a model, not a raw string, per the "no raw dicts"
# convention. The master resume is loaded server-side, so the client only sends
# the JD.
class TailorRequest(BaseModel):
    text: str
