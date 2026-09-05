import { useCallback, useEffect, useState } from "react";
import type { StatusSuggestion } from "./types";
import { listSuggestions } from "./api";

export interface SuggestionsState {
  suggestions: StatusSuggestion[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

// Fetch the user's pending status suggestions (the Gmail pipeline's review
// queue). Same shape as useApplications: load on mount, expose refetch so the
// review panel can refresh after accepting or dismissing one.
export function useSuggestions(): SuggestionsState {
  const [suggestions, setSuggestions] = useState<StatusSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // silent === true skips the loading flag, for background polling / focus
  // refetches that shouldn't flash over what's on screen.
  const load = useCallback(async (silent?: unknown) => {
    const showLoading = silent !== true;
    if (showLoading) setLoading(true);
    setError(null);
    try {
      setSuggestions(await listSuggestions());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  // Load on mount, then poll every 60s and refetch on focus, so suggestions the
  // Gmail watcher stages in the background surface without a manual refresh.
  useEffect(() => {
    load();
    const poll = setInterval(() => load(true), 60_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") load(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      clearInterval(poll);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [load]);

  return { suggestions, loading, error, refetch: load };
}
