// The editing shell: all sections stacked on one scrollable page with a sticky
// header (back, career-stage toggle, Save). Shown to returning users who already
// have a master resume. Purely presentational — the orchestrator passes the
// pre-wired section nodes and the save handlers.

import type { ShellProps } from "./shell";
import { CareerStageToggle } from "./CareerStageToggle";

const primaryBtn =
  "rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover active:bg-accent-press disabled:opacity-60 disabled:shadow-none";

export function ResumeEditor({
  sections,
  careerStage,
  onCareerStageChange,
  canSave,
  saving,
  saveError,
  saved,
  onSave,
  onClose,
}: ShellProps) {
  return (
    <div className="flex flex-col">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-line bg-base/95 px-6 py-4 backdrop-blur">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            aria-label="Back"
            className="grid size-8 place-items-center rounded-interactive text-ink-muted transition-colors hover:text-ink"
          >
            <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M15 18l-6-6 6-6" />
            </svg>
          </button>
          <h1 className="text-base font-semibold text-ink">Your resume</h1>
        </div>
        <div className="flex items-center gap-3">
          <CareerStageToggle value={careerStage} onChange={onCareerStageChange} />
          {saveError ? (
            <span className="text-[13px] text-ink-soft">{saveError}</span>
          ) : (
            saved && <span className="text-[13px] text-ink-muted">Saved</span>
          )}
          <button
            type="button"
            onClick={onSave}
            disabled={!canSave || saving}
            className={primaryBtn}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-6 py-8">
        {sections.map((s) => (
          <div key={s.id}>{s.node}</div>
        ))}
      </div>
    </div>
  );
}
