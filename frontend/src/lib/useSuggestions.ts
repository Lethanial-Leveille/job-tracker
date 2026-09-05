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

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSuggestions(await listSuggestions());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { suggestions, loading, error, refetch: load };
}
