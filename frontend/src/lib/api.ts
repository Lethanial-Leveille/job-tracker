// Typed wrappers around the backend HTTP API. Components never call fetch
// directly — they call these, so the URL shape, auth, and error handling live in
// one place. All calls go through the Vite proxy at /api (see vite.config.ts),
// which strips /api and forwards to the backend on :8000.

import { clearToken, getToken } from "./auth";
import type {
  Application,
  ApplicationCreateInput,
  FitReport,
  DiscoveredJob,
  DiscoveryRun,
  TargetCompany,
  TargetCompanyInput,
  ParsedFromUrl,
  ParsedJob,
  Resume,
  ResumeVersion,
  StatusEvent,
  StatusSuggestion,
} from "./types";

const BASE = "/api";

// One shared entry point for every AUTHENTICATED call. It attaches the bearer
// token, and on a 401 (token missing, expired, or invalid) it clears the token
// and fires a window event so the app drops back to the login screen. It returns
// the raw Response so each caller can read JSON, a Blob, or nothing (204) as it
// needs. Login is deliberately NOT routed through here (see below).
//
// allowStatuses lets a caller opt out of the throw for specific non-ok codes it
// wants to handle itself — e.g. getMasterResume passes [404] to read "no master
// yet" as null instead of an error. A 401 is always handled (never swallowable).
async function request(
  path: string,
  options: RequestInit = {},
  allowStatuses: number[] = [],
): Promise<Response> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.dispatchEvent(new Event("auth:unauthorized"));
  }
  if (!res.ok && !allowStatuses.includes(res.status)) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await request(path);
  return res.json() as Promise<T>;
}

// --- Auth -------------------------------------------------------------------

// Log in with email + password and return the access token. This is a direct
// fetch, NOT via request(), on purpose: a 401 here means "wrong password" — a
// message for the login form — not "log the user out globally," so it must not
// fire the unauthorized event or it would loop.
export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    throw new Error(
      res.status === 401
        ? "Incorrect email or password"
        : "Login failed, please try again",
    );
  }
  const data = (await res.json()) as { access_token: string };
  return data.access_token;
}

// --- Applications -----------------------------------------------------------

export function listApplications(): Promise<Application[]> {
  return getJson<Application[]>("/applications");
}

// POST a new application. The backend returns the created row (with its new id
// and timestamps), which we hand back so the caller can use it.
export async function createApplication(
  input: ApplicationCreateInput,
): Promise<Application> {
  const res = await request("/applications", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.json() as Promise<Application>;
}

// POST raw posting text and get back Claude's extraction. This never creates a
// row — the flow uses the result to pre-fill fields you then review and submit.
export async function parseJobDescription(text: string): Promise<ParsedJob> {
  const res = await request("/applications/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json() as Promise<ParsedJob>;
}

// POST a posting LINK. The server fetches the page, turns it into text, and
// runs the same parser the paste path uses — so this returns the extraction
// plus the text it was read from, which the caller stores as jd_text.
//
// 400 is allowed through rather than thrown by request(), because a fetch
// failure is the ROUTINE outcome here, not an exception: some job sites block
// scripts, some pages need a browser to render, some links are dead. The
// backend puts a sentence written for a person in `detail`, and this rethrows
// exactly that so the add screen can show it above the paste box. Every other
// non-ok status keeps request()'s generic error, including the 502 that means
// the page was read but could not be parsed — different problem, and pasting
// the same text again would not fix it.
export async function parseJobUrl(url: string): Promise<ParsedFromUrl> {
  const res = await request(
    "/applications/parse-url",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    },
    [400],
  );
  if (res.status === 400) {
    const body = (await res.json()) as { detail?: string };
    throw new Error(
      body.detail ?? "Could not read that link. Paste the posting text instead.",
    );
  }
  return res.json() as Promise<ParsedFromUrl>;
}

// --- Target companies -------------------------------------------------------

export function listCompanies(): Promise<TargetCompany[]> {
  return getJson<TargetCompany[]>("/companies");
}

// Which identifier fields each system needs, served rather than duplicated so
// the form and the backend validator cannot drift apart.
export function atsRequirements(): Promise<Record<string, string[]>> {
  return getJson<Record<string, string[]>>("/companies/requirements");
}

// 422 is allowed through so the specific message survives. The backend names
// the field you actually have to fill — "workday needs a site id, e.g.
// external_experienced" — and request()'s generic error would throw that away
// for "Request failed: 422", which tells you nothing about which box is empty.
async function saveCompany(
  path: string,
  method: "POST" | "PATCH",
  input: Partial<TargetCompanyInput>,
): Promise<TargetCompany> {
  const res = await request(
    path,
    {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
    [422],
  );
  if (res.status === 422) {
    const body = (await res.json()) as { detail?: unknown };
    const detail = body.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : // FastAPI's own validation errors arrive as a list of objects.
          ((detail as { msg?: string }[])?.[0]?.msg ?? "That company is incomplete"),
    );
  }
  return res.json() as Promise<TargetCompany>;
}

export function createCompany(input: TargetCompanyInput): Promise<TargetCompany> {
  return saveCompany("/companies", "POST", input);
}

export function updateCompany(
  id: string,
  input: Partial<TargetCompanyInput>,
): Promise<TargetCompany> {
  return saveCompany(`/companies/${id}`, "PATCH", input);
}

export async function deleteCompany(id: string): Promise<void> {
  await request(`/companies/${id}`, { method: "DELETE" });
}

// --- Discovery feed ---------------------------------------------------------

// The undecided inbox, newest posting first.
export function listDiscovered(): Promise<DiscoveredJob[]> {
  return getJson<DiscoveredJob[]>("/discovered");
}

// Start a pull. Returns immediately with the run that was started, NOT with the
// result — the work happens in the background.
//
// It has to. The site is behind Cloudflare, which abandons any request the
// origin has not answered within 100 seconds and returns a 524. A first pull
// downloads a 12MB feed, classifies hundreds of titles, and reads up to fifty
// postings one at a time, so a synchronous version would report a failure for a
// run that was working fine.
//
// 409 is allowed through rather than thrown: a pull already running is a normal
// thing to bump into (the nightly job may be going), not an error worth an
// alarming message.
export async function startPull(): Promise<DiscoveryRun | "already-running"> {
  const res = await request("/discovered/refresh", { method: "POST" }, [409]);
  if (res.status === 409) return "already-running";
  return res.json() as Promise<DiscoveryRun>;
}

// The most recent run, finished or not. Polled while one is in flight, and read
// once on load so the page can say what the last night did.
export function latestRun(): Promise<DiscoveryRun | null> {
  return getJson<DiscoveryRun | null>("/discovered/runs/latest");
}

// File a discovery into the pipeline. Answers with the created application,
// which is the row you now care about.
export async function acceptDiscovered(id: string): Promise<Application> {
  const res = await request(`/discovered/${id}/accept`, { method: "POST" });
  return res.json() as Promise<Application>;
}

// Turn one down. The row is kept server-side so tomorrow's pull cannot offer it
// again, but it leaves the inbox.
export async function dismissDiscovered(id: string): Promise<DiscoveredJob> {
  const res = await request(`/discovered/${id}/dismiss`, { method: "POST" });
  return res.json() as Promise<DiscoveredJob>;
}

// PATCH an existing application. The backend's update schema treats every field
// as optional and its service applies only the keys actually sent
// (`model_dump(exclude_unset=True)`), so a body may carry one field or all of
// them. Hence Partial<...>: the edit form sends the whole object, while a single
// field change (flipping status from the row) sends just `{ status }` and leaves
// everything else untouched. Returns the row.
export async function updateApplication(
  id: string,
  input: Partial<ApplicationCreateInput>,
): Promise<Application> {
  const res = await request(`/applications/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.json() as Promise<Application>;
}

// DELETE an application. The backend answers 204 No Content, so there is no body
// to parse — request() already confirmed it worked.
export async function deleteApplication(id: string): Promise<void> {
  await request(`/applications/${id}`, { method: "DELETE" });
}

// POST to judge this application's stated requirements against your master
// resume. POST, not GET, because it spends a paid API call and writes the result
// back to the row. The cached result of the last run arrives on the application
// itself as `fit_report`, so displaying an existing report costs nothing.
export async function computeFit(applicationId: string): Promise<FitReport> {
  const res = await request(`/applications/${applicationId}/fit`, {
    method: "POST",
  });
  return res.json() as Promise<FitReport>;
}

// --- Resume tailoring -------------------------------------------------------

// POST a job description and get back the tailored Resume (JSON). Runs Opus on
// the backend; this is the draft you review before rendering or saving.
export async function tailorResume(text: string): Promise<Resume> {
  const res = await request("/resume/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  return res.json() as Promise<Resume>;
}

// POST a reviewed Resume and get back the rendered PDF plus the name to save it
// under. The FILENAME COMES FROM THE SERVER, in Content-Disposition, rather than
// being built here: the Lastname_Firstname_Resume_Company convention is a rule
// about the resume, so it belongs next to the renderer that knows the contact
// name, and building it in both places would let them drift.
//
// `company` tags a tailored download with the employer it was tailored for.
// `gradDate` picks which of two true graduation dates prints ("alternate" is the
// later one, for programs that only accept underclassmen); omitted, the resume's
// own setting stands.
export interface RenderedResume {
  blob: Blob;
  filename: string;
}

// Pulls filename="..." out of a Content-Disposition header. Deliberately reads
// the plain `filename` and not RFC 6266's `filename*`: the server already folds
// the value to ASCII, so the two always agree and the simple one needs no
// percent-decoding. Falls back if the header is missing or malformed.
function filenameFrom(header: string | null): string {
  const match = header?.match(/filename="([^"]+)"/);
  return match?.[1] ?? "resume.pdf";
}

// The general-purpose resume: the master reduced to one page, derived server-side
// on every call rather than stored. Feed the result straight to renderResume()
// (optionally with a gradDate) to get the PDF — one render path for base and
// tailored alike, so the two can never disagree about format.
export async function getBaseResume(): Promise<Resume> {
  const res = await request("/resume/base");
  return (await res.json()) as Resume;
}

export async function renderResume(
  resume: Resume,
  company?: string,
  gradDate?: "primary" | "alternate",
): Promise<RenderedResume> {
  const params = new URLSearchParams();
  if (company) params.set("company", company);
  if (gradDate) params.set("grad_date", gradDate);
  const query = params.toString();
  const res = await request(`/resume/render${query ? `?${query}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(resume),
  });
  return {
    blob: await res.blob(),
    filename: filenameFrom(res.headers.get("Content-Disposition")),
  };
}

// GET an application's saved tailored resume versions, newest first.
export function listResumeVersions(
  applicationId: string,
): Promise<ResumeVersion[]> {
  return getJson<ResumeVersion[]>(
    `/resume/versions?application_id=${encodeURIComponent(applicationId)}`,
  );
}

// POST to persist a reviewed tailored resume as a version for an application.
// Explicit save (never automatic): the UI calls this only after you approve a
// draft. Returns the stored version.
export async function saveResumeVersion(input: {
  application_id: string;
  resume: Resume;
  job_description: string;
}): Promise<ResumeVersion> {
  const res = await request("/resume/versions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return res.json() as Promise<ResumeVersion>;
}

// --- Master resume ----------------------------------------------------------

// GET the current user's master resume, or null if they don't have one yet. The
// backend 404s when none exists; we allow that status and return null so the
// builder opens blank for a first-time user rather than treating it as an error.
export async function getMasterResume(): Promise<Resume | null> {
  const res = await request("/resume/master", {}, [404]);
  if (res.status === 404) {
    return null;
  }
  return res.json() as Promise<Resume>;
}

// PUT the user's master resume (create-or-replace). The backend accepts a
// partial, half-filled Resume, so this doubles as the "save work in progress"
// call. Returns the stored resume.
export async function saveMasterResume(resume: Resume): Promise<Resume> {
  const res = await request("/resume/master", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(resume),
  });
  return res.json() as Promise<Resume>;
}

// GET an application's status history, oldest first.
export function listApplicationTimeline(
  applicationId: string,
): Promise<StatusEvent[]> {
  return getJson<StatusEvent[]>(
    `/applications/${encodeURIComponent(applicationId)}/timeline`,
  );
}

// DELETE one history entry (a corrected misclick). 204, no body. Does not change
// the application's current status.
export async function deleteTimelineEvent(
  applicationId: string,
  eventId: string,
): Promise<void> {
  await request(
    `/applications/${encodeURIComponent(applicationId)}/timeline/${encodeURIComponent(eventId)}`,
    { method: "DELETE" },
  );
}

// --- Status suggestions -----------------------------------------------------

// GET the current user's pending status suggestions (from the Gmail pipeline).
export function listSuggestions(): Promise<StatusSuggestion[]> {
  return getJson<StatusSuggestion[]>("/suggestions");
}

// Accept a suggestion, applying its status to an application. applicationId is
// needed only for an unresolved suggestion (ambiguous → pick a candidate;
// unmatched → pick any application); a resolved one ignores it.
export async function acceptSuggestion(
  id: string,
  applicationId?: string,
): Promise<StatusSuggestion> {
  const res = await request(`/suggestions/${id}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ application_id: applicationId ?? null }),
  });
  return res.json() as Promise<StatusSuggestion>;
}

// Dismiss a suggestion without changing any application.
export async function dismissSuggestion(id: string): Promise<StatusSuggestion> {
  const res = await request(`/suggestions/${id}/dismiss`, { method: "POST" });
  return res.json() as Promise<StatusSuggestion>;
}

// Create a new application from an unmatched suggestion's email (employer, role,
// and status from the message; you fill in the URL/deadline later), then accept
// it. Returns the created application.
export async function createApplicationFromSuggestion(
  id: string,
): Promise<Application> {
  const res = await request(`/suggestions/${id}/create-application`, {
    method: "POST",
  });
  return res.json() as Promise<Application>;
}
