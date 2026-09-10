import { useCallback, useEffect, useState } from "react";
import type { DiscoveredJob, PullResult } from "./types";
import { listDiscovered, refreshDiscovered } from "./api";

export interface DiscoveredState {
  jobs: DiscoveredJob[];
  loading: boolean;
  error: string | null;
  // True while a pull is running. Separate from `loading` because they mean
  // different things to the person watching: loading is "fetching the list you
  // already have", pulling is "downloading sixteen thousand postings and
  // reading the new ones", which takes a while and needs saying so.
  pulling: boolean;
  lastPull: PullResult | null;
  refetch: () => void;
  pull: () => Promise<void>;
}

// The discovery inbox: jobs the feed found, waiting to be accepted or dismissed.
//
// Same shape as useSuggestions with one deliberate difference: no polling. A
// suggestion can arrive at any moment because the Gmail watcher runs on a short
// cycle, so polling earns its keep there. The discovery pull runs once a night,
// so a 60-second poll would spend a request a minute to notice something that
// changes while you are asleep. Refetching on focus covers it.
export function useDiscovered(): DiscoveredState {
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pulling, setPulling] = useState(false);
  const [lastPull, setLastPull] = useState<PullResult | null>(null);

  const load = useCallback(async (silent?: unknown) => {
    const showLoading = silent !== true;
    if (showLoading) setLoading(true);
    setError(null);
    try {
      setJobs(await listDiscovered());
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load discoveries");
    } finally {
      if (showLoading) setLoading(false);
    }
  }, []);

  const pull = useCallback(async () => {
    setPulling(true);
    setError(null);
    try {
      const result = await refreshDiscovered();
      setLastPull(result);
      // Reload silently: the list is about to change under a spinner that is
      // already showing, and a second one would just flash.
      await load(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "The pull failed");
    } finally {
      setPulling(false);
    }
  }, [load]);

  useEffect(() => {
    load();
    const onVisible = () => {
      if (document.visibilityState === "visible") load(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [load]);

  return { jobs, loading, error, pulling, lastPull, refetch: load, pull };
}
