// The builder's brain. Loads the master resume, holds the editable draft, wires
// each section to its slice, owns save, and picks the shell: the guided wizard
// for first-time users (no master yet), the scrollable editor for returning ones.
//
// The loaded resume seeds a child's useState, so the fetch-then-edit split is
// clean: ResumeBuilder handles loading/error, and only mounts the editing brain
// (Inner) once there's real data to seed from.

import { useState } from "react";
import type { ReactNode } from "react";
import type { Resume } from "../../lib/types";
import { useMasterResume } from "../../lib/useMasterResume";
import { ContactFields } from "./ContactFields";
import { EducationSection } from "./EducationSection";
import { ExperienceSection } from "./ExperienceSection";
import { ProjectsSection } from "./ProjectsSection";
import { SkillsSection } from "./SkillsSection";
import { ResumeEditor } from "./ResumeEditor";
import { ResumeWizard } from "./ResumeWizard";
import type { CareerStage, ResumeSection } from "./shell";

interface Props {
  onClose: () => void;
}

export function ResumeBuilder({ onClose }: Props) {
  const { resume, isNew, loading, error, refetch, save } = useMasterResume();

  if (loading) {
    return <CenterState>Loading your resume…</CenterState>;
  }
  if (error) {
    return (
      <CenterState>
        <p className="text-sm text-ink-soft">{error}</p>
        <button
          type="button"
          onClick={refetch}
          className="mt-3 rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
        >
          Retry
        </button>
      </CenterState>
    );
  }

  // Remount when the loaded identity flips so Inner re-seeds its draft state.
  return <Inner key={isNew ? "new" : "existing"} initial={resume} isNew={isNew} save={save} onClose={onClose} />;
}

function Inner({
  initial,
  isNew,
  save,
  onClose,
}: {
  initial: Resume;
  isNew: boolean;
  save: (next: Resume) => Promise<Resume>;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Resume>(initial);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // One updater for the whole draft; a fresh edit clears the "Saved" flag so the
  // indicator only shows when the on-screen state actually matches what's stored.
  const update = (changes: Partial<Resume>) => {
    setDraft((d) => ({ ...d, ...changes }));
    setSaved(false);
  };

  // Each section is pre-bound to its slice here, so the shells only arrange nodes.
  const sections: ResumeSection[] = [
    { id: "contact", title: "Contact", node: <ContactFields value={draft.contact} onChange={(c) => update({ contact: c })} /> },
    { id: "experience", title: "Experience", node: <ExperienceSection items={draft.experience} onChange={(x) => update({ experience: x })} /> },
    { id: "education", title: "Education", node: <EducationSection items={draft.education} onChange={(e) => update({ education: e })} /> },
    { id: "skills", title: "Skills", node: <SkillsSection items={draft.skills} onChange={(s) => update({ skills: s })} /> },
    { id: "projects", title: "Projects", node: <ProjectsSection items={draft.projects} onChange={(p) => update({ projects: p })} /> },
  ];

  // The backend's one hard requirement is contact.name; everything else can be
  // saved half-filled (partial resumes validate).
  const canSave = draft.contact.name.trim() !== "";

  async function handleSave() {
    if (!canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      await save(draft);
      // First-time users finish the wizard and return to the app; returning
      // users stay in the editor with a "Saved" confirmation.
      if (isNew) {
        onClose();
      } else {
        setSaved(true);
      }
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Could not save your resume");
    } finally {
      setSaving(false);
    }
  }

  const shellProps = {
    sections,
    careerStage: (draft.career_stage ?? "student") as CareerStage,
    onCareerStageChange: (stage: CareerStage) => update({ career_stage: stage }),
    canSave,
    saving,
    saveError,
    saved,
    onSave: handleSave,
    onClose,
  };

  return isNew ? <ResumeWizard {...shellProps} /> : <ResumeEditor {...shellProps} />;
}

function CenterState({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      {children}
    </div>
  );
}
