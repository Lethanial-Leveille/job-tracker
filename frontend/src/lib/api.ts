// Typed wrappers around the backend HTTP API. Components never call fetch
// directly — they call these, so the URL shape and error handling live in one
// place. All calls go through the Vite proxy at /api (see vite.config.ts),
// which strips /api and forwards to the backend on :8000.

import type { Application, ApplicationCreateInput } from "./types";

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
