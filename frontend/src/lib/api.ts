// Typed wrappers around the backend HTTP API. Components never call fetch
// directly — they call these, so the URL shape and error handling live in one
// place. All calls go through the Vite proxy at /api (see vite.config.ts),
// which strips /api and forwards to the backend on :8000.

import type {
  Application,
  ApplicationCreateInput,
  ParsedJob,
  Resume,
  ResumeVersion,
} from "./types";

const BASE = "/api";

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function listApplications(): Promise<Application[]> {
  return getJson<Application[]>("/applications");
}

// POST a new application. Unlike a GET, this carries a JSON body, so we set the
// method, the Content-Type header, and JSON.stringify the payload. The backend
// returns the created row (with its new id and timestamps), which we hand back
// so the caller can use it if it wants.
export async function createApplication(
  input: ApplicationCreateInput,
): Promise<Application> {
  const res = await fetch(`${BASE}/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<Application>;
}

// POST raw posting text and get back Claude's extraction. This never creates a
// row — the modal uses the result to pre-fill fields you then review and submit.
export async function parseJobDescription(text: string): Promise<ParsedJob> {
  const res = await fetch(`${BASE}/applications/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<ParsedJob>;
}

// PATCH an existing application. The backend's update schema treats every field
// as optional, so sending the full edited object is valid — it just overwrites
// each field with what the form holds. Returns the updated row.
export async function updateApplication(
  id: string,
  input: ApplicationCreateInput,
): Promise<Application> {
  const res = await fetch(`${BASE}/applications/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<Application>;
}

// DELETE an application. The backend answers 204 No Content on success, so there
// is no body to parse — we just confirm it worked and return nothing.
export async function deleteApplication(id: string): Promise<void> {
  const res = await fetch(`${BASE}/applications/${id}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
}

// --- Resume tailoring -------------------------------------------------------

// POST a job description and get back the tailored Resume (JSON). Runs Opus on
// the backend; this is the draft you review before rendering or saving. Never
// auto-submits anything (hard rule #1).
export async function tailorResume(text: string): Promise<Resume> {
  const res = await fetch(`${BASE}/resume/tailor`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<Resume>;
}

// POST a reviewed Resume and get back the rendered PDF as a Blob (binary, not
// JSON), which the caller turns into a download. No Opus call — rendering is
// pure, so re-rendering after an edit is free.
export async function renderResume(resume: Resume): Promise<Blob> {
  const res = await fetch(`${BASE}/resume/render`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(resume),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
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
  const res = await fetch(`${BASE}/resume/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<ResumeVersion>;
}
