import { useCallback, useEffect, useState } from "react";
import type { Application, ApplicationStatus } from "./types";
import { listApplications, updateApplication } from "./api";

export interface ApplicationsState {
  applications: Application[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
  // Change one row's status without a round trip through the edit form.
  setStatus: (id: string, status: ApplicationStatus) => void;
  // A failed write, kept separate from `error` on purpose — see below.
  saveError: string | null;
  dismissSaveError: () => void;
}

// Fetch the application list and expose it as state. Lives at App level so both
// the sidebar (total count) and the table (the list) read from a single fetch.
//
// `load` is the fetch itself, wrapped in useCallback so it's a stable function
// (same reference every render) — that lets us both run it once on mount and
// hand it back as `refetch` for callers to trigger again (e.g. after creating a
// new application).
export function useApplications(): ApplicationsState {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  // Two error channels, deliberately. `error` means "the list itself could not
  // be loaded", and the page replaces the whole table with a message. A failed
  // status write is nothing like that — the list on screen is still perfectly
  // good — so it goes to `saveError`, which renders as a dismissible banner
  // above an otherwise working table.
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listApplications();
      setApplications(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // An OPTIMISTIC UPDATE: change the local copy first so the badge flips the
  // instant you pick a value, then send the PATCH, and put the old value back
  // if the server rejects it. The alternative — await the PATCH, then refetch
  // the entire list — is what the rest of this app does, and it means staring
  // at a stale badge through two network round trips for a one word change.
  //
  // We only ever send `{ status }`. The server applies just the keys it
  // receives, so nothing else on the row can be clobbered by this call.
  const setStatus = useCallback(
    async (id: string, status: ApplicationStatus) => {
      const previous = applications.find((app) => app.id === id)?.status;
      // Unknown row, or no actual change: nothing to send.
      if (previous === undefined || previous === status) return;

      setApplications((prev) =>
        prev.map((app) => (app.id === id ? { ...app, status } : app)),
      );
      setSaveError(null);

      try {
        await updateApplication(id, { status });
      } catch {
        // Roll back to exactly what it was, and say so. Silently reverting
        // would look like the click just didn't register.
        setApplications((prev) =>
          prev.map((app) =>
            app.id === id ? { ...app, status: previous } : app,
          ),
        );
        setSaveError("Could not save that status change. Nothing was updated.");
      }
    },
    // Depends on `applications` because it reads the previous status out of it.
    // That makes this function change identity whenever the list does, which is
    // fine at this size: the table re-renders on a list change anyway.
    [applications],
  );

  const dismissSaveError = useCallback(() => setSaveError(null), []);

  return {
    applications,
    loading,
    error,
    refetch: load,
    setStatus,
    saveError,
    dismissSaveError,
  };
}
