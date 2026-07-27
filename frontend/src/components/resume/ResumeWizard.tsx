// The onboarding shell: one step at a time with Back/Next, ending in a review +
// Save. Shown to first-time users (no master resume yet). Career stage is the
// FIRST step because it shapes the whole resume. Purely presentational — steps
// are the orchestrator's pre-wired section nodes, bracketed by a stage step and a
// review step.

import { useState } from "react";
import type { ShellProps } from "./shell";
import { CareerStageToggle } from "./CareerStageToggle";

const primaryBtn =
  "rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover active:bg-accent-press disabled:opacity-60 disabled:shadow-none";
const secondaryBtn =
  "rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-40";

export function ResumeWizard({
  sections,
  careerStage,
  onCareerStageChange,
  canSave,
  saving,
  saveError,
  onSave,
  onClose,
}: ShellProps) {
  // Step keys: a leading "stage" step, one per section, then a trailing "review".
  const steps = ["stage", ...sections.map((s) => s.id), "review"];
  const [i, setI] = useState(0);
  const total = steps.length;
  const key = steps[i];
  const isFirst = i === 0;
  const isReview = key === "review";
  const section = sections.find((s) => s.id === key);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col px-6 py-8">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
          Step {i + 1} of {total}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="grid size-8 place-items-center rounded-interactive text-ink-muted transition-colors hover:text-ink"
        >
          <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${((i + 1) / total) * 100}%` }} />
      </div>

      <div className="mt-8">
        {key === "stage" && (
          <div className="flex flex-col gap-4">
            <h1 className="font-serif text-[30px] font-semibold text-ink">Who is this resume for?</h1>
            <p className="text-sm text-ink-soft">
              This sets the layout. Students lead with education; professionals lead with experience.
            </p>
            <CareerStageToggle value={careerStage} onChange={onCareerStageChange} />
          </div>
        )}

        {section && (
          <div className="flex flex-col gap-4">
            <h1 className="font-serif text-[30px] font-semibold text-ink">{section.title}</h1>
            {section.node}
          </div>
        )}

        {isReview && (
          <div className="flex flex-col gap-4">
            <h1 className="font-serif text-[30px] font-semibold text-ink">Review and save</h1>
            <p className="text-sm text-ink-soft">
              You can edit any of this later.{canSave ? "" : " Add your name before saving."}
            </p>
            {saveError && <p className="text-[13px] text-ink-soft">{saveError}</p>}
          </div>
        )}
      </div>

      <div className="mt-8 flex items-center justify-between">
        <button type="button" onClick={() => setI(i - 1)} disabled={isFirst} className={secondaryBtn}>
          Back
        </button>
        {isReview ? (
          <button type="button" onClick={onSave} disabled={!canSave || saving} className={primaryBtn}>
            {saving ? "Saving…" : "Save resume"}
          </button>
        ) : (
          <button type="button" onClick={() => setI(i + 1)} className={primaryBtn}>
            Next
          </button>
        )}
      </div>
    </div>
  );
}
