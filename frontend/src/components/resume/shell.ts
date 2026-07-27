// Shared contract between the builder's brain (ResumeBuilder) and its two
// presentational shells (ResumeWizard, ResumeEditor). Kept in its own tiny module
// so both shells and the orchestrator import the same types without a circular
// dependency (the orchestrator imports the shells; the shells only import this).

import type { ReactNode } from "react";

export type CareerStage = "student" | "professional";

// One section, pre-wired to the draft by the orchestrator. The shells only
// arrange these nodes — the wizard shows one per step, the editor stacks them.
export interface ResumeSection {
  id: string;
  title: string;
  node: ReactNode;
}

export interface ShellProps {
  sections: ResumeSection[];
  careerStage: CareerStage;
  onCareerStageChange: (stage: CareerStage) => void;
  canSave: boolean;
  saving: boolean;
  saveError: string | null;
  saved: boolean;
  onSave: () => void;
  onClose: () => void;
}
