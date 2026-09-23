// Shared contract between the builder's brain (ResumeBuilder) and its two
// presentational shells (ResumeWizard, ResumeEditor). Kept in its own tiny module
// so both shells and the orchestrator import the same types without a circular
// dependency (the orchestrator imports the shells; the shells only import this).

import type { ReactNode } from "react";

// Which flavour of resume goes out. Replaces the old student/professional
// choice, which picked a section arrangement for two different people; there is
// one person now, and the daily question is software or embedded.
export type ResumeTrack = "swe" | "embedded";

// One section, pre-wired to the draft by the orchestrator. The shells only
// arrange these nodes — the wizard shows one per step, the editor stacks them.
export interface ResumeSection {
  id: string;
  title: string;
  node: ReactNode;
}

export interface ShellProps {
  sections: ResumeSection[];
  track: ResumeTrack;
  onTrackChange: (track: ResumeTrack) => void;
  canSave: boolean;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
  onSave: () => void;
  onClose: () => void;
}
