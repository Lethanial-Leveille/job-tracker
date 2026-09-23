import { useState } from "react";
import { downloadBaseResume } from "./downloadBase";
import type { ResumeTrack } from "./shell";

// One button per resume flavour, at the top of the editor.
//
// Both sit here rather than behind the flavour toggle because printing is not
// the same decision as editing. The toggle sets what your resume IS; these ask
// for a copy of either one right now, and needing to flip a setting, download,
// and flip it back is how you send the wrong resume to the next three
// companies.
//
// Muted, not accented: Save is the primary action on this screen and the design
// system keeps purple scarce enough to mean something.

const TRACKS: { value: ResumeTrack; label: string }[] = [
  { value: "swe", label: "Software PDF" },
  { value: "embedded", label: "Embedded PDF" },
];

export function DownloadBaseButtons({ unsaved }: { unsaved: boolean }) {
  const [busy, setBusy] = useState<ResumeTrack | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function download(track: ResumeTrack) {
    setBusy(track);
    setError(null);
    try {
      await downloadBaseResume(track);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not build that PDF");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {TRACKS.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => download(t.value)}
          disabled={busy !== null || unsaved}
          // Says WHY it is disabled. A dead button with no explanation is worse
          // than no button.
          title={
            unsaved
              ? "Save first — these are built from your saved resume"
              : `The one-page ${t.label.replace(" PDF", "")} resume`
          }
          className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-40"
        >
          {busy === t.value ? "Building…" : t.label}
        </button>
      ))}
      {error && <span className="text-[12px] text-ink-soft">{error}</span>}
    </div>
  );
}
