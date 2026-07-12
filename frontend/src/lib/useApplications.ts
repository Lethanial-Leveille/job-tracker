import { useCallback, useEffect, useState } from "react";
import type { Application } from "./types";
import { listApplications } from "./api";

export interface ApplicationsState {
  applications: Application[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

// Fetch the application list and expose it as state. Lives at App level so both
// the sidebar (total count) and the table (the list) read from a single fetch.
//
// `load` is the fetch itself, wrapped in useCallback so it's a stable function
// (same reference every render) — that lets us both run it once on mount and
// hand it back as `refetch` for callers to trigger again (e.g. after creating a
// new application).
//
// LATER: for a snappier create flow, swap the post-create refetch for an
// optimistic update — append the newly created row to `applications` directly
// and skip this extra network round trip. Refetch first, optimize once it works.
export function useApplications(): ApplicationsState {
  const [applications, setApplications] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  return { applications, loading, error, refetch: load };
}
