// The general-purpose resume: what to print when there is no job to tailor
// against — a career fair, a club, a workshop.
//
// It is DERIVED from the master by the server on every open (GET /resume/base),
// never stored. That is deliberate: a second stored resume would be a second
// thing to edit and a second thing to drift out of date, which is exactly the
// problem the YAML file used to cause against the database. You tune this
// resume by REORDERING bullets in the builder, because the derivation keeps the
// strongest-first ones and the page trim cuts from the end.
//
// The grad-date control is a toggle rather than two downloads on purpose: both
// May 2028 and May 2029 are true (94 credit hours against a 128-credit degree),
// and which one prints is a per-download choice, so the server takes it as a
// query parameter instead of it being stored on the resume. One resume, two
// renders, no second document to keep in sync.

import { useCallback, useEffect, useState } from "react";
import { getBaseResume, renderResume } from "../../lib/api";
import type { Resume } from "../../lib/types";
import { PdfPreview } from "./PdfPreview";

type GradDate = "primary" | "alternate";

export function BaseResumePanel({ onBack }: { onBack: () => void }) {
  const [resume, setResume] = useState<Resume | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [filename, setFilename] = useState("resume.pdf");
  const [gradDate, setGradDate] = useState<GradDate>("primary");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load the derived resume once. Re-rendering for a different grad date reuses
  // it rather than re-deriving, since the switch is a render-time concern.
  useEffect(() => {
    let live = true;
    getBaseResume()
      .then((r) => {
        if (live) setResume(r);
      })
      .catch((e: unknown) => {
        if (live) setError(e instanceof Error ? e.message : "Could not load your resume");
      });
    return () => {
      live = false;
    };
  }, []);

  const render = useCallback(
    async (which: GradDate) => {
      if (!resume) return;
      setLoading(true);
      setError(null);
      try {
        const out = await renderResume(resume, undefined, which);
        setBlob(out.blob);
        setFilename(out.filename);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Could not render the PDF");
      } finally {
        setLoading(false);
      }
    },
    [resume],
  );

  useEffect(() => {
    if (resume) void render(gradDate);
  }, [resume, gradDate, render]);

  // The ONLY path that writes a file to disk. Everything above stays in memory.
  function download() {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <button
            type="button"
            onClick={onBack}
            className="mb-1 text-sm text-ink-soft transition-colors hover:text-ink"
          >
            &larr; Back to builder
          </button>
          <h2 className="text-base font-medium text-ink">General resume</h2>
          <p className="text-sm text-ink-soft">
            Built from your master. Reorder bullets in the builder to change what prints.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div
            role="group"
            aria-label="Graduation date"
            className="flex rounded-interactive border border-line bg-surface p-0.5"
          >
            {(
              [
                ["primary", "May 2028"],
                ["alternate", "May 2029"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={gradDate === value}
                onClick={() => setGradDate(value)}
                className={`rounded-interactive px-3 py-1.5 text-sm transition-colors ${
                  gradDate === value
                    ? "bg-surface-raised font-medium text-ink"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={download}
            disabled={!blob || loading}
            className="rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
          >
            Download PDF
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <PdfPreview blob={blob} loading={loading} className="min-h-[70vh] flex-1" />
    </div>
  );
}
