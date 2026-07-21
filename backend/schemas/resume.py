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

from pydantic import BaseModel


class Contact(BaseModel):
    """Header block. Fixed identity — tailoring never touches any of this."""

    name: str
    location: str | None = None
    phone: str | None = None
    email: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class Education(BaseModel):
    """A school. `coursework` is tailorable (surface courses relevant to a job);
    the rest (institution, degree, gpa) is fixed fact."""

    institution: str
    degree: str
    location: str | None = None
    dates: str | None = None          # freeform, e.g. "Expected May 2029"
    gpa: str | None = None            # e.g. "3.73 / 4.00"
    # Pydantic copies list defaults per-instance, so the usual mutable-default
    # trap (every instance sharing one list) does not apply here.
    honors: list[str] = []            # e.g. ["Dean's List"]
    coursework: list[str] = []        # tailorable: select the relevant courses


class SkillGroup(BaseModel):
    """One labeled row of skills, e.g. category "Languages", items [Python, C]."""

    category: str
    items: list[str] = []


class Experience(BaseModel):
    """A job. `bullets` is a bank: hold every bullet here, let tailoring keep the
    strongest ~4 and rephrase them for the target job."""

    organization: str
    role: str
    location: str | None = None
    dates: str | None = None
    bullets: list[str] = []


class Project(BaseModel):
    """A project. The master holds ALL of them; tailoring selects a subset of
    projects (and, within each, a subset of bullets). `links` is a list because
    one project can have several repos (M.I.L.E.S. has two)."""

    name: str
    tools: list[str] = []
    links: list[str] = []
    dates: str | None = None
    bullets: list[str] = []


class Resume(BaseModel):
    """A complete resume. Section order here is the order the renderer prints.

    What tailoring MAY change: rewrite `summary`; reorder/select `projects` and
    `experience` entries; select/reorder/rephrase `bullets`; select `coursework`
    and reorder `skills`. What it may NOT change: any name, org, role, date,
    degree, gpa, or project name — and it may never add a bullet, skill, or
    number that isn't already in the master (hard rule #2, never invent).
    """

    contact: Contact
    summary: str | None = None        # the one free-text spot tailoring may rewrite
    education: list[Education] = []
    skills: list[SkillGroup] = []
    experience: list[Experience] = []
    projects: list[Project] = []      # the full bank; tailoring keeps a subset
