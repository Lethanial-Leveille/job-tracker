import { useCallback, useEffect, useState } from "react";
import type { Resume } from "./types";
import { getMasterResume, saveMasterResume } from "./api";

// A fresh blank resume to seed the builder for a first-time user (the backend
// 404s when none exists, which api.getMasterResume returns as null). It's a
// FACTORY, not a shared const, so each call returns its own nested arrays and
// objects — otherwise every "new" resume would share (and corrupt) one set of
// arrays, the classic mutable-default trap. career_stage starts "student" to
// match the backend default; the wizard's first step lets the user switch it.
function blankResume(): Resume {
  return {
    career_stage: "student",
    contact: { name: "" },
    summary: "",
    education: [],
    skills: [],
    experience: [],
    projects: [],
  };
}

export interface MasterResumeState {
  resume: Resume;
  // true when the user has no saved master yet — the signal to show the guided
  // wizard rather than the scrollable editor. Flips to false after the first save.
  isNew: boolean;
  loading: boolean;
  error: string | null;
  refetch: () => void;
  save: (next: Resume) => Promise<Resume>;
}

// Load the current user's master resume and expose it as editable state. Unlike
// useApplications this is not lifted to App — nothing outside the builder reads
// it — so a builder view calls this hook directly.
//
// `load` is wrapped in useCallback so it's a stable reference: run once on mount,
// and handed back as `refetch`. A 404 (no master yet) is NOT an error here — it's
// a first-time user, so we seed a blank resume and mark isNew.
export function useMasterResume(): MasterResumeState {
  const [resume, setResume] = useState<Resume>(blankResume);
  const [isNew, setIsNew] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMasterResume();
      if (data === null) {
        setResume(blankResume());
        setIsNew(true);
      } else {
        setResume(data);
        setIsNew(false);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load your resume");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Persist and adopt the returned resume as current state. Once saved, the user
  // is no longer new, so isNew flips — a subsequent visit shows the editor. The
  // caller awaits this and owns its own saving/spinner state (mirroring how the
  // application forms track `saving` locally).
  const save = useCallback(async (next: Resume): Promise<Resume> => {
    const saved = await saveMasterResume(next);
    setResume(saved);
    setIsNew(false);
    return saved;
  }, []);

  return { resume, isNew, loading, error, refetch: load, save };
}
