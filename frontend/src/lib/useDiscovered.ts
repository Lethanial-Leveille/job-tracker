import { useCallback, useEffect, useRef, useState } from "react";
import type { DiscoveredJob, DiscoveryRun } from "./types";
import { latestRun, listDiscovered, startPull } from "./api";

export interface DiscoveredState {
  jobs: DiscoveredJob[];
  loading: boolean;
  error: string | null;
  // The most recent pull, running or finished. This is what makes a background
  // run visible: a quiet night, a run in progress, and a run that died all look
  // like an inbox that did not change, and only this tells them apart.
  run: DiscoveryRun | null;
  // True from pressing the button until the run reports it is over. Distinct
  // from `loading`, which is only about fetching the list you already have.
  pulling: boolean;
  refetch: () => void;
  pull: () => Promise<void>;
}

// How often to ask whether the run has finished. Five seconds is slow enough
// that a ten-minute first run costs a manageable number of requests, and fast
// enough that a thirty-second one does not feel stuck.
const POLL_MS = 5_000;

// The discovery inbox: jobs the feed found, waiting to be accepted or dismissed.
//
// The pull is asynchronous, so this hook has two jobs rather than one. It loads
// the list, and it watches whatever run is in flight — including one it did not
// start, because the nightly job may be running when you open the page.
export function useDiscovered(): DiscoveredState {
  const [jobs, setJobs] = useState<DiscoveredJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const timer = useRef<number | null>(null);

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

  // One poll tick. Kept out of an effect so both the button and the initial
  // load can start watching, and so a run started by the nightly job is picked
  // up the same way as one you started yourself.
  const watch = useCallback(async () => {
    let current: DiscoveryRun | null = null;
    try {
      current = await latestRun();
    } catch {
      // A failed poll is not a failed run. Keep the last known state on screen
      // rather than replacing a real result with an error from asking about it.
      return;
    }
    setRun(current);
    if (current?.state === "running") {
      timer.current = window.setTimeout(watch, POLL_MS);
    } else if (current) {
      // It finished while we were watching, so the list has changed underneath.
      await load(true);
    }
  }, [load]);

  const pull = useCallback(async () => {
    setError(null);
    try {
      const started = await startPull();
      if (started === "already-running") {
        // Not an error. The nightly job may be going, or another tab started
        // one — either way the right move is to watch it rather than complain.
        await watch();
        return;
      }
      setRun(started);
      timer.current = window.setTimeout(watch, POLL_MS);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start the pull");
    }
  }, [watch]);

  useEffect(() => {
    load();
    // Check on load too: a run may already be going from the schedule.
    watch();
    const onVisible = () => {
      if (document.visibilityState === "visible") load(true);
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
    // watch and load are stable useCallbacks; re-running this on every render
    // would start a new poll chain each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    jobs,
    loading,
    error,
    run,
    pulling: run?.state === "running",
    refetch: load,
    pull,
  };
}
