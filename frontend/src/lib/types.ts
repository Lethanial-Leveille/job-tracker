// Mirror of the backend Pydantic schemas (backend/schemas/application.py) and
// model enums (backend/models/application.py). Kept in sync by hand for v1 —
// if a column is added or an enum value changes on the backend, update it here
// too. These are the exact shapes GET /applications returns.

// "scholarship" is DORMANT: the tracker went jobs-only, so nothing in the UI
// creates or filters by it any more. The value stays in the union because the
// backend enum still has it and older rows may still carry it — dropping it
// here would make those rows fail to typecheck for no gain.
export type ApplicationType = "internship" | "scholarship";

export type ApplicationStatus =
  | "discovered"
  | "drafting"
  | "ready"
  | "applied"
  | "recruiter_engaged"
  | "phone_screen"
  | "technical_interview"
  | "onsite"
  | "offer"
  | "accepted"
  | "declined"
  | "rejected"
  | "ghosted"
  | "missed_deadline";

export type Priority = "low" | "medium" | "high";

// The canonical role families. Mirror of backend/schemas/roles.py — kept in sync
// by hand like the rest of this file. Postings title the same job many ways, so
// the parser classifies each into one of these and the list renders it, while
// role_or_program keeps the title exactly as posted.
export const ROLE_FAMILIES = [
  "Software Engineer Intern",
  "Embedded Engineer Intern",
  "AI and ML Engineer Intern",
  "Frontend Engineer Intern",
  "Backend Engineer Intern",
  "Data Engineer Intern",
  "Hardware Engineer Intern",
  "Other",
] as const;

export type RoleFamily = (typeof ROLE_FAMILIES)[number];

// The parser's extras with no column of their own, stored in the jd_parsed blob
// and surfaced in the detail drawer's "From the posting" section.
export interface JdParsed {
  summary?: string | null;
  salary?: string | null;
  location?: string | null;
  key_requirements?: string[];
}

// --- Requirement matching ---------------------------------------------------
// Mirror of backend/schemas/fit.py. Deliberately NOT a probability of getting
// the job: it compares the posting's stated requirements against your master
// resume, item by item, and shows the evidence for each call.

// "unknown" is never produced by the model — the backend assigns it to any
// requirement the model failed to answer for, so a dropped item can't quietly
// read as met.
export type RequirementVerdict = "met" | "partial" | "missing" | "unknown";

export interface RequirementMatch {
  requirement: string;
  verdict: RequirementVerdict;
  evidence: string | null;
}

export interface FitReport {
  matches: RequirementMatch[];
  met_count: number;
  partial_count: number;
  total: number;
  computed_at: string; // ISO datetime
}

export interface Application {
  id: string;
  type: ApplicationType;
  organization: string;
  role_or_program: string;
  // The normalized role. Null on rows created before the parser started
  // classifying, so every read site needs a fallback to role_or_program.
  role_family: RoleFamily | null;
  posting_url: string;
  status: ApplicationStatus;
  priority: Priority;
  deadline: string | null; // ISO date, e.g. "2026-07-14"
  notes: string | null;
  jd_parsed: JdParsed | null; // parser extras (salary, summary, requirements…)
  jd_text: string | null; // the raw pasted JD, used as tailoring input
  // The cached requirement-match report, or null if never computed for this
  // row. Written only by POST /applications/{id}/fit, never by create or edit.
  fit_report: FitReport | null;
  created_at: string; // ISO datetime
  updated_at: string; // ISO datetime
}

// What POST /applications/parse returns. Mirror of the backend ParsedJob schema
// (backend/schemas/parsing.py). This is Claude's extraction, not a stored row —
// the modal uses it to pre-fill fields, which you review before saving.
export interface ParsedJob {
  type: ApplicationType;
  organization: string;
  role_or_program: string;
  role_family: RoleFamily;
  deadline: string | null; // ISO date or null if the posting didn't state one
  salary: string | null;
  location: string | null;
  summary: string | null;
  key_requirements: string[];
}

// The body we send to POST /applications. Mirror of the backend ApplicationCreate
// schema: the four identifying fields are required; status and priority are
// optional (the backend fills discovered/medium if omitted); deadline and notes
// are optional. Server-managed fields (id, timestamps, jd_parsed) are absent —
// the client never sends those.
export interface ApplicationCreateInput {
  type: ApplicationType;
  organization: string;
  role_or_program: string;
  posting_url: string;
  role_family?: RoleFamily | null;
  status?: ApplicationStatus;
  priority?: Priority;
  deadline?: string | null;
  notes?: string | null;
  // The parser's extras (salary, summary, requirements) with no column of their
  // own. Set only on an autofilled create; omitted on manual create and edit.
  jd_parsed?: JdParsed | null;
  // The raw pasted JD, carried in on an autofilled create so tailoring can later
  // run against the real posting. Omitted on a manual create.
  jd_text?: string | null;
}

// --- Resume tailoring -------------------------------------------------------
// Mirror of backend/schemas/resume.py: the one Resume shape shared by the master
// file, tailoring in/out, and the renderer. Dates are freeform strings, not real
// dates (resumes show "Expected May 2029"). Kept in sync by hand like the rest.

export interface Contact {
  name: string;
  location?: string | null;
  phone?: string | null;
  email?: string | null;
  linkedin?: string | null;
  github?: string | null;
  website?: string | null;
}

export interface Education {
  institution: string;
  degree: string;
  location?: string | null;
  dates?: string | null;
  gpa?: string | null;
  honors: string[];
  coursework: string[];
}

export interface SkillGroup {
  category: string;
  items: string[];
}

export interface Experience {
  organization: string;
  role: string;
  location?: string | null;
  dates?: string | null;
  bullets: string[];
}

export interface Project {
  name: string;
  tools: string[];
  links: string[];
  dates?: string | null;
  bullets: string[];
}

export interface Resume {
  // Rendering arrangement, mirrors backend schemas/resume.py. "student" puts
  // education first with GPA and coursework shown; "professional" leads with
  // experience and hides GPA/coursework. Optional because the server defaults it
  // to "student", so a resume saved before this field existed stays valid.
  career_stage?: "student" | "professional";
  contact: Contact;
  summary?: string | null;
  education: Education[];
  skills: SkillGroup[];
  experience: Experience[];
  projects: Project[];
}

// A saved, tailored resume version. Mirror of backend ResumeVersionRead.
export interface ResumeVersion {
  id: string;
  application_id: string;
  resume: Resume;
  job_description: string;
  created_at: string; // ISO datetime
}
