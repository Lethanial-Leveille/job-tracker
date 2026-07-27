// Typed wrappers around the backend HTTP API. Components never call fetch
// directly — they call these, so the URL shape, auth, and error handling live in
// one place. All calls go through the Vite proxy at /api (see vite.config.ts),
// which strips /api and forwards to the backend on :8000.

import { clearToken, getToken } from "./auth";
import type {
  Application,
  ApplicationCreateInput,
  ParsedJob,
  Resume,
  ResumeVersion,
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

// PATCH an existing application. The backend's update schema treats every field
// as optional, so sending the full edited object is valid. Returns the row.
export async function updateApplication(
  id: string,
  input: ApplicationCreateInput,
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

// POST a reviewed Resume and get back the rendered PDF as a Blob (binary, not
// JSON), which the caller turns into a download.
export async function renderResume(resume: Resume): Promise<Blob> {
  const res = await request("/resume/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(resume),
  });
  return res.blob();
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
