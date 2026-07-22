import { useState } from "react";
import type { Application, Resume } from "../../lib/types";
import { renderResume, saveResumeVersion, tailorResume } from "../../lib/api";
import { DrawerHeader } from "../layout/Drawer";

// Tailor a resume for one application — the body of an elevated drawer that
// stacks over the detail panel. Flow honors hard rule #1: generate a draft,
// review it here, then explicitly download the PDF and/or save the version.
//
// Two-endpoint split shows here: tailorResume runs the Opus call once; renderResume
// turns that same (free) JSON into a PDF, so re-downloading never re-runs Opus.

interface Props {
  application: Application;
  onClose: () => void;
  onSaved: () => void; // so the detail panel's versions list can refresh
}

const labelClass =
  "flex flex-col gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-muted";
const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";
const secondaryBtn =
  "rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50";

export function TailorPanel({ application, onClose, onSaved }: Props) {
  const [jd, setJd] = useState(application.jd_text ?? "");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [tailored, setTailored] = useState<Resume | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function generate() {
    if (jd.trim() === "") return;
    setGenerating(true);
    setGenError(null);
    setSaved(false);
    setActionError(null);
    try {
      setTailored(await tailorResume(jd));
    } catch (err: unknown) {
      setGenError(err instanceof Error ? err.message : "Could not tailor the resume");
    } finally {
      setGenerating(false);
    }
  }

  async function download() {
    if (!tailored) return;
    setDownloading(true);
    setActionError(null);
    try {
      const blob = await renderResume(tailored);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `resume-${application.organization}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not render the PDF");
    } finally {
      setDownloading(false);
    }
  }

  async function save() {
    if (!tailored) return;
    setSaving(true);
    setActionError(null);
    try {
      await saveResumeVersion({
        application_id: application.id,
        resume: tailored,
        job_description: jd,
      });
      setSaved(true);
      onSaved();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Could not save the version");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <DrawerHeader onClose={onClose}>
        <h2 className="text-lg font-semibold text-ink">Tailor resume</h2>
        <div className="mt-0.5 truncate text-sm text-ink-soft">
          {application.organization} — {application.role_or_program}
        </div>
      </DrawerHeader>

      <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-6 py-5">
        <label className={labelClass}>
          Job description
          <textarea
            value={jd}
            onChange={(e) => setJd(e.target.value)}
            rows={5}
            placeholder="Paste the job description to tailor against…"
            className={`${fieldClass} resize-none`}
          />
        </label>

        <div className="flex items-center justify-between gap-3">
          <span className="text-[11.5px] text-ink-muted">
            Claude drafts a one-page resume from your master. Review before saving.
          </span>
          <button
            type="button"
            onClick={generate}
            disabled={generating || jd.trim() === ""}
            className="shrink-0 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover disabled:opacity-60"
          >
            {generating ? "Tailoring…" : tailored ? "Regenerate" : "Generate tailored resume"}
          </button>
        </div>

        {genError && (
          <p className="rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink">
            {genError}
          </p>
        )}

        {tailored && (
          <div className="flex flex-col gap-4 rounded-frame border border-line bg-base p-4">
            <ResumePreview resume={tailored} />
          </div>
        )}
      </div>

      {tailored && (
        <div className="flex items-center justify-between gap-3 border-t border-line bg-surface px-6 py-3.5">
          <span className="text-[12px] text-ink-muted">
            {saved ? `Saved to ${application.organization}.` : actionError ?? ""}
          </span>
          <div className="flex gap-2.5">
            <button type="button" onClick={download} disabled={downloading} className={secondaryBtn}>
              {downloading ? "Rendering…" : "Download PDF"}
            </button>
            <button type="button" onClick={save} disabled={saving || saved} className={secondaryBtn}>
              {saving ? "Saving…" : saved ? "Saved" : "Save version"}
            </button>
          </div>
        </div>
      )}
    </>
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
