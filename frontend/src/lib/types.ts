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
  // The online assessment (coding test / take-home / recorded screen). Mirrors
  // the backend enum; added Sept 2026.
  | "assessment"
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
  // The hard requirements ("You have", "Minimum qualifications").
  key_requirements?: string[];
  // The "We prefer" list, kept separate. Absent on rows stored before the
  // parser started splitting the two.
  preferred_qualifications?: string[];
}

// --- Requirement matching ---------------------------------------------------
// Mirror of backend/schemas/fit.py. Deliberately NOT a probability of getting
// the job: it compares the posting's stated requirements against your master
// resume, item by item, and shows the evidence for each call.

// "unknown" is never produced by the model — the backend assigns it to any
// requirement the model failed to answer for, so a dropped item can't quietly
// read as met.
// "unstated" is for eligibility facts a resume cannot answer (work
// authorization, clearance). It is not a softer "missing" — missing means you do
// not meet it, unstated means nobody can tell from this document.
export type RequirementVerdict =
  | "met"
  | "partial"
  | "missing"
  | "unstated"
  | "unknown";

// Whether an item gates the application or differentiates it. Judged the same
// way; reported separately.
export type RequirementKind = "required" | "preferred";

export interface RequirementMatch {
  requirement: string;
  verdict: RequirementVerdict;
  evidence: string | null;
  kind: RequirementKind;
}

export interface FitReport {
  matches: RequirementMatch[];
  met_count: number;
  partial_count: number;
  unstated_count: number;
  // Required items only, so the headline never shifts meaning.
  total: number;
  preferred_met_count: number;
  preferred_partial_count: number;
  preferred_total: number;
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
  // Derived server-side from the status history: the FIRST time this row
  // reached `applied`. Null until it has been. Not a stored column — see
  // backend/services/application.py.
  applied_at: string | null; // ISO datetime
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
  preferred_qualifications: string[];
}

// What POST /applications/parse-url returns. Mirror of the backend ParsedFromUrl
// schema. The parsed fields are NESTED rather than spread alongside the rest,
// matching the backend, so a field added to ParsedJob later can never collide
// with one of the three below.
//
// jd_text is the load-bearing extra: on the paste path the raw posting is
// already in hand, but on the link path the server is the only one that ever
// saw it, and resume tailoring reads it later. `posting_url` is the link AFTER
// redirects, which is the one worth storing. `source` names the path the fetch
// took ("workday", "generic"), and a compound value like "workday+generic"
// means a known job board's API came up empty and the page got scraped instead.
export interface ParsedFromUrl {
  parsed: ParsedJob;
  jd_text: string;
  posting_url: string;
  source: string;
}

// --- Discovery feed ---------------------------------------------------------

// What reading a discovered posting found about graduation timing. Mirror of
// the backend Eligibility model (backend/services/eligibility.py).
//
// "unclear" is the common and correct answer: most postings say nothing about
// when you must graduate, and silence is not a rejection. It is distinct from
// the whole object being null, which means the posting was never read — a site
// that needs a browser, or a link that had already gone dead.
export interface Eligibility {
  // "eligible_early" is the one worth understanding: the posting wants a
  // graduation year you can only claim by using your EARLIER date. Not a
  // rejection, and not a plain yes either — a decision to make deliberately.
  //
  // "too_early" never appears in the inbox. Those postings closed before you
  // can finish (a new-grad role, or a cycle already gone), so the backend files
  // them away rather than handing you a row you could only dismiss. It is in
  // this union because the field is stored on rows you can still go and find.
  verdict:
    | "eligible"
    | "eligible_early"
    | "too_early"
    | "too_late"
    | "unclear";
  wanted_years: number[];
  your_years: number[];
  // The sentence that produced the verdict. Always shown: a verdict you cannot
  // check is one you either obey blindly or ignore, and both are worse than none.
  evidence: string | null;
  // A class-standing phrase ("open to rising seniors"), reported without a
  // verdict because whether it includes you depends on credit hours at a date a
  // year out. Surfaced so you can judge it; never guessed at.
  standing: string | null;
}

// A job the feed found, waiting for you to accept or dismiss. Mirror of the
// backend DiscoveredJobRead schema.
export interface DiscoveredJob {
  id: string;
  source: string;
  organization: string;
  role_or_program: string;
  posting_url: string;
  location: string | null;
  posted_at: string | null; // ISO date, per the employer, not when we found it
  state: "pending" | "accepted" | "dismissed" | "filtered";
  role_family: RoleFamily | null;
  // Applications this might already be. Non-empty means "show a warning", never
  // "hide the row" — reapplying to a role in a new cycle is a real thing to do.
  possible_application_ids: string[] | null;
  eligibility: Eligibility | null;
  enriched_at: string | null;
  application_id: string | null;
  created_at: string;
}

// One pull attempt. The pull runs in the background now — the site is behind
// Cloudflare, which abandons any request the origin has not answered in 100
// seconds, and a first pull is comfortably past that — so this record is how a
// run becomes visible at all.
//
// Without it, an inbox that did not change could mean the feed was quiet, the
// run is still going, or the run died. Those need to look different.
export interface DiscoveryRun {
  id: string;
  state: "running" | "succeeded" | "failed";
  started_at: string;
  finished_at: string | null;
  fetched: number;
  staged: number;
  duplicates: number;
  enriched: number;
  ruled_out: number;
  sources: Record<string, unknown> | null;
  error: string | null;
}

// What one run of the feed pull did. `dropped` is keyed by reason, which is the
// only thing that distinguishes a quiet night from a filter that has silently
// stopped recognizing the feed's labels.
export interface PullResult {
  fetched: number;
  kept: number;
  staged: number;
  duplicates: number;
  enriched: number;
  // Cumulative count of discoveries ruled out on graduation timing. Surfaced so
  // an inbox emptied by a broken check is distinguishable from a quiet night.
  ruled_out: number;
  dropped: Record<string, number>;
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
  // Never rendered into the PDF. Stored so postings that require the right to
  // work without sponsorship can actually be answered.
  work_authorization?: string | null;
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

// --- Status suggestions (the Gmail pipeline's review side) -------------------

export type SuggestionState = "pending" | "accepted" | "dismissed";

// The email that produced a suggestion, shown as evidence in the review UI.
export interface SuggestionEmail {
  from_email: string;
  from_name?: string | null;
  subject?: string | null;
  snippet?: string | null;
  received_at: string; // ISO datetime
}

// One staged status change awaiting the user's decision. Mirror of backend
// SuggestionRead. application_id set = resolved to one app; candidate ids set =
// ambiguous (pick one); both null = unmatched (couldn't tie it to an app).
export interface StatusSuggestion {
  id: string;
  suggested_status: ApplicationStatus;
  reason: string;
  application_id: string | null;
  candidate_application_ids: string[] | null;
  state: SuggestionState;
  created_at: string; // ISO datetime
  email: SuggestionEmail | null;
}

// --- Status history (the application timeline) -------------------------------

export type StatusEventSource = "manual" | "email";

// One entry in an application's status history. Mirror of backend StatusEventRead.
// from_status null marks the application's first status (when it was added).
export interface StatusEvent {
  id: string;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus;
  source: StatusEventSource;
  created_at: string; // ISO datetime
}
