// The editing shell: all sections stacked on one scrollable page with a sticky
// header (back, career-stage toggle, Save). Shown to returning users who already
// have a master resume. Purely presentational — the orchestrator passes the
// pre-wired section nodes and the save handlers.

import { Link } from "react-router-dom";
import type { ShellProps } from "./shell";
import { ResumeTrackToggle } from "./ResumeTrackToggle";
import { DownloadBaseButtons } from "./DownloadBaseButtons";

const primaryBtn =
  "rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink transition-shadow transition-colors hover:bg-accent-hover hover:shadow-glow active:bg-accent-press disabled:opacity-60";

export function ResumeEditor({
  sections,
  track,
  onTrackChange,
  canSave,
  unsaved,
  saving,
  saveError,
  saved,
  onSave,
}: ShellProps) {
  return (
    <div className="flex flex-col">
      <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b border-line bg-base px-4 py-4 sm:px-6 relative before:pointer-events-none before:absolute before:inset-x-0 before:bottom-full before:h-10 before:bg-base">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-semibold text-ink">Your resume</h1>
        </div>
        <div className="flex items-center gap-3">
          {/* The general resume is DERIVED from what is saved here, so it is a
              sibling of the editor rather than a section inside it. */}
          <Link
            to="/resume/base"
            className="text-[13px] text-ink-soft transition-colors hover:text-ink"
          >
            General resume
          </Link>
          <ResumeTrackToggle value={track} onChange={onTrackChange} />
          {/* Both flavours, one click each. Disabled while there are unsaved
              edits: the server derives these from the STORED master, so a
              download taken mid-edit would quietly be the previous version. */}
          <DownloadBaseButtons unsaved={unsaved} />
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

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8 sm:px-6">
        {sections.map((s) => (
          <div key={s.id}>{s.node}</div>
        ))}
      </div>
    </div>
  );
}
