import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Application, ApplicationStatus, Resume, ResumeVersion } from "../../lib/types";
import {
  listResumeVersions,
  renderResume,
  saveResumeVersion,
  tailorResume,
} from "../../lib/api";
import { gradDateHint } from "../../lib/gradHint";
import { isPreSubmit } from "./statuses";

// The Tailor tab: draft a resume for this application, review it, download or
// save it, and see what has already been saved. Previously a second drawer
// stacked on top of the detail drawer; now it is simply the other half of the
// application's page.
//
// Hard rule #1 still holds exactly as before: Claude drafts, you review, and
// nothing is downloaded or saved until you say so. Generating a draft is not
// submitting anything.
//
// Two-endpoint split: tailorResume runs the Opus call once; renderResume turns
// that same (free) JSON into a PDF, so re-downloading never re-runs Opus.

interface Props {
  application: Application;
  onStatusChange: (id: string, status: ApplicationStatus) => void;
}

const secondaryBtn =
  "rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function TailorTab({ application, onStatusChange }: Props) {
  const [jd, setJd] = useState(application.jd_text ?? "");
  const [versions, setVersions] = useState<ResumeVersion[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [tailored, setTailored] = useState<Resume | null>(null);
  // Which of two true graduation dates prints. Off means 2028 (the default);
  // on means the later date, for programs that only accept underclassmen. It is
  // a per-download choice and deliberately NOT remembered or inferred: tailoring
  // is forbidden from picking it, because guessing an eligibility rule out of
  // posting text and guessing wrong prints a date you did not intend.
  const [laterGradDate, setLaterGradDate] = useState(false);
  // Read straight from the posting already in memory: no call, no cost. It only
  // suggests, and cites what it matched so the suggestion can be judged.
  const gradHint = useMemo(() => gradDateHint(application), [application]);
  const hintDisagrees =
    gradHint !== null && (gradHint.suggest === "alternate") !== laterGradDate;
  const [downloading, setDownloading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Fires at most once per mount, so the auto-start below can never loop or
  // re-run when you edit the job description.
  const autoStarted = useRef(false);

  const generate = useCallback(async (text: string) => {
    if (text.trim() === "") return;
    setGenerating(true);
    setGenError(null);
    setSaved(false);
    setActionError(null);
    try {
      setTailored(await tailorResume(text));
    } catch (err: unknown) {
      setGenError(err instanceof Error ? err.message : "Could not tailor the resume");
    } finally {
      setGenerating(false);
    }
  }, []);

  // Load what's already saved for this application.
  useEffect(() => {
    let live = true;
    setVersions(null);
    listResumeVersions(application.id)
      .then((v) => live && setVersions(v))
      .catch(() => live && setVersions([]));
    return () => {
      live = false;
    };
  }, [application.id]);

  // GENERATE ON OPEN. If this application arrived with a pasted posting and has
  // no saved version yet, the Generate click was pure ceremony: the job
  // description was already in the box and the answer was never going to differ.
  // So start as soon as the tab opens.
  //
  // Deliberately gated on OPENING the tab rather than on creating the row. Each
  // run is a paid Opus call, and you add rows you never end up applying to, so
  // opening the tab is the cheapest honest signal that you actually want one.
  //
  // The decision reads application.jd_text, not the editable `jd` state, so
  // typing in the box can never trigger a run.
  useEffect(() => {
    if (autoStarted.current) return;
    if (versions === null) return; // still loading; don't decide yet
    if (versions.length > 0) return; // already has one, show it instead
    if ((application.jd_text ?? "").trim() === "") return; // nothing to run on
    autoStarted.current = true;
    generate(application.jd_text ?? "");
  }, [versions, application.jd_text, generate]);

  async function downloadResume(resume: Resume, versionId?: string) {
    if (versionId) setDownloadingId(versionId);
    else setDownloading(true);
    setActionError(null);
    try {
      // Pass the employer so the file arrives as
      // Leveille_Lethanial_Resume_Stripe.pdf, and use the server's name rather
      // than inventing one here — the convention lives with the renderer.
      const { blob, filename } = await renderResume(
        resume,
        application.organization,
        laterGradDate ? "alternate" : undefined,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not render the PDF");
    } finally {
      setDownloadingId(null);
      setDownloading(false);
    }
  }

  async function save() {
    if (!tailored) return;
    setSaving(true);
    setActionError(null);
    try {
      const version = await saveResumeVersion({
        application_id: application.id,
        resume: tailored,
        job_description: jd,
      });
      setSaved(true);
      // Newest first, matching the order the API returns. Appending locally
      // avoids a refetch for a row we already have in hand.
      setVersions((prev) => [version, ...(prev ?? [])]);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not save the version");
    } finally {
      setSaving(false);
    }
  }

  // Saving a tailored resume is the step right before actually applying, so
  // offer the status change here instead of making you go back for it. Only
  // when the row hasn't already moved past the pre-submit stages.
  const notYetApplied = isPreSubmit(application.status);

  return (
    <div className="flex flex-col gap-8 pb-8">
      <Section title="Job description">
        <textarea
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          rows={6}
          placeholder="Paste the job description to tailor against…"
          className="w-full resize-y rounded-interactive border border-line bg-base px-3.5 py-3 text-sm leading-relaxed text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[11.5px] text-ink-muted">
            Claude drafts a one-page resume from your master. Review before saving.
          </span>
          <button
            type="button"
            onClick={() => generate(jd)}
            disabled={generating || jd.trim() === ""}
            className="shrink-0 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover disabled:opacity-60"
          >
            {generating ? "Tailoring…" : tailored ? "Regenerate" : "Generate tailored resume"}
          </button>
        </div>
        {genError && (
          <p className="rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink">
            {genError}
          </p>
        )}
      </Section>

      {generating && !tailored && (
        <div className="flex flex-col items-center gap-4 rounded-frame border border-line bg-surface py-14 text-center">
          <div className="size-11 animate-spin rounded-full border-2 border-line-strong border-t-accent shadow-glow motion-reduce:animate-none" />
          <div>
            <p className="text-[15px] font-medium text-ink">Drafting your resume</p>
            <p className="mt-1 text-[12.5px] text-ink-muted">
              Selecting and rephrasing bullets from your master resume.
            </p>
          </div>
        </div>
      )}

      {tailored && (
        <Section title="Draft">
          <div className="rounded-frame border border-line bg-surface p-5">
            <ResumePreview resume={tailored} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-[12px] text-ink-muted">
              {/* The hint outranks the idle message only while it disagrees with
                  the current setting, so it reads as something to act on rather
                  than a permanent badge you stop seeing. */}
              {hintDisagrees && !saved && !actionError
                ? `This posting suggests the ${
                    gradHint?.suggest === "alternate" ? "later" : "earlier"
                  } grad date: "${gradHint?.evidence}"`
                : saved
                  ? `Saved to ${application.organization}.`
                  : actionError ?? "Nothing is saved until you say so."}
            </span>
            <div className="flex flex-wrap items-center gap-2.5">
              <label
                className="flex cursor-pointer items-center gap-1.5 text-[12px] text-ink-muted"
                title={
                  gradHint
                    ? `Posting says: "${gradHint.evidence}"`
                    : "This posting says nothing about class standing."
                }
              >
                <input
                  type="checkbox"
                  checked={laterGradDate}
                  onChange={(e) => setLaterGradDate(e.target.checked)}
                  className="size-3.5 accent-accent"
                />
                Later grad date
                {hintDisagrees && (
                  <span className="text-accent" aria-hidden="true">
                    •
                  </span>
                )}
              </label>
              <button
                type="button"
                onClick={() => downloadResume(tailored)}
                disabled={downloading}
                className={secondaryBtn}
              >
                {downloading ? "Rendering…" : "Download PDF"}
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving || saved}
                className={secondaryBtn}
              >
                {saving ? "Saving…" : saved ? "Saved" : "Save version"}
              </button>
              {saved && notYetApplied && (
                <button
                  type="button"
                  onClick={() => onStatusChange(application.id, "applied")}
                  className="rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover"
                >
                  Mark as applied
                </button>
              )}
            </div>
          </div>
        </Section>
      )}

      <Section title="Saved versions">
        {versions === null ? (
          <p className="text-[12px] text-ink-muted">Loading…</p>
        ) : versions.length === 0 ? (
          <p className="text-[12px] text-ink-muted">
            {(application.jd_text ?? "").trim() === ""
              ? "No versions yet. Paste the job description above to draft one."
              : "No versions saved yet."}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {versions.map((v) => (
              <div
                key={v.id}
                className="flex items-center gap-3 rounded-frame border border-line bg-surface px-3.5 py-3"
              >
                <span className="grid size-[30px] shrink-0 place-items-center rounded-lg border border-line-strong bg-surface-hover text-ink-muted">
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                    <path d="M14 3v5h5" />
                  </svg>
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-ink">
                    Tailored resume
                  </div>
                  <div className="text-[11px] text-ink-muted">Saved {fmtDate(v.created_at)}</div>
                </div>
                <button
                  type="button"
                  onClick={() => downloadResume(v.resume, v.id)}
                  disabled={downloadingId === v.id}
                  className="rounded-interactive px-2.5 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink disabled:opacity-50"
                >
                  {downloadingId === v.id ? "…" : "PDF"}
                </button>
              </div>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

// A readable rendering of the tailored draft so you can judge it without opening
// the PDF. Calm data on dark; no purple here.
function ResumePreview({ resume }: { resume: Resume }) {
  return (
    <div className="flex flex-col gap-4 text-sm text-ink-soft">
      {resume.summary && <p className="text-ink">{resume.summary}</p>}

      {resume.experience.length > 0 && (
        <PreviewSection title="Experience">
          {resume.experience.map((exp, i) => (
            <div key={i}>
              <p className="font-medium text-ink">
                {exp.role} — {exp.organization}
              </p>
              <BulletList bullets={exp.bullets} />
            </div>
          ))}
        </PreviewSection>
      )}

      {resume.projects.length > 0 && (
        <PreviewSection title="Projects">
          {resume.projects.map((proj, i) => (
            <div key={i}>
              <p className="font-medium text-ink">{proj.name}</p>
              <BulletList bullets={proj.bullets} />
            </div>
          ))}
        </PreviewSection>
      )}

      {resume.skills.length > 0 && (
        <PreviewSection title="Skills">
          {resume.skills.map((group, i) => (
            <p key={i}>
              <span className="text-ink">{group.category}:</span> {group.items.join(", ")}
            </p>
          ))}
        </PreviewSection>
      )}
    </div>
  );
}

function PreviewSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">{title}</h3>
      {children}
    </div>
  );
}

function BulletList({ bullets }: { bullets: string[] }) {
  if (bullets.length === 0) return null;
  return (
    <ul className="mt-1 list-disc pl-5 text-ink-soft">
      {bullets.map((b, i) => (
        <li key={i}>{b}</li>
      ))}
    </ul>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
        {title}
        <span className="h-px flex-1 bg-line" />
      </div>
      {children}
    </div>
  );
}
