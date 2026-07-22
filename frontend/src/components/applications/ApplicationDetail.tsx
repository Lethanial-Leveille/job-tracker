import { useEffect, useState } from "react";
import type { Application, ResumeVersion } from "../../lib/types";
import { monogram, statusLabel, priorityLabel, typeLabel } from "../../lib/format";
import { listResumeVersions, renderResume } from "../../lib/api";
import { DrawerHeader } from "../layout/Drawer";

// The detail panel body (rendered inside a Drawer). Clicking a row opens this.
// It is where the parser's extras finally become visible: the "From the posting"
// section surfaces the jd_parsed summary, compensation, location, and
// requirements that were stored but never shown before.

interface Props {
  application: Application;
  onClose: () => void;
  onEdit: (application: Application) => void;
  onTailor: (application: Application) => void;
  onDelete: (application: Application) => void;
}

function fmt(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function ApplicationDetail({
  application,
  onClose,
  onEdit,
  onTailor,
  onDelete,
}: Props) {
  const [versions, setVersions] = useState<ResumeVersion[] | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  // Load this application's saved tailored resumes when the panel opens.
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

  async function downloadVersion(v: ResumeVersion) {
    setDownloadingId(v.id);
    try {
      const blob = await renderResume(v.resume);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `resume-${application.organization}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloadingId(null);
    }
  }

  const jd = application.jd_parsed;
  const hasPosting =
    jd &&
    (jd.summary || jd.salary || jd.location || (jd.key_requirements?.length ?? 0) > 0);
  const isOffer = application.status === "offer";

  return (
    <>
      <DrawerHeader onClose={onClose}>
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-[10px] border border-line-strong bg-surface-hover text-sm font-semibold text-ink-soft">
            {monogram(application.organization)}
          </span>
          <div className="min-w-0">
            <h2 id="detail-title" className="truncate text-lg font-semibold text-ink">
              {application.organization}
            </h2>
            <div className="truncate text-sm text-ink-soft">
              {application.role_or_program}
            </div>
          </div>
        </div>
      </DrawerHeader>

      <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-6 py-5">
        {/* Chips */}
        <div className="flex flex-wrap gap-2">
          <Pill>{typeLabel(application.type)}</Pill>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${
              isOffer
                ? "border-transparent bg-accent text-ink shadow-glow"
                : "border-line-strong bg-surface text-ink-soft"
            }`}
          >
            <span className={`size-1.5 rounded-full ${isOffer ? "bg-ink" : "bg-ink-soft"}`} />
            {statusLabel(application.status)}
          </span>
          <Pill>Priority: {priorityLabel(application.priority)}</Pill>
        </div>

        {/* Facts */}
        <div className="grid grid-cols-2 gap-x-5 gap-y-4">
          <Fact label="Deadline" value={fmt(application.deadline)} />
          <Fact label="Added" value={fmt(application.created_at)} />
          <div className="col-span-2">
            <FactLabel>Posting link</FactLabel>
            {application.posting_url ? (
              <a
                href={application.posting_url}
                target="_blank"
                rel="noopener noreferrer"
                className="break-all text-[13.5px] text-accent hover:underline"
              >
                {application.posting_url}
              </a>
            ) : (
              <span className="text-[13.5px] text-ink-muted">—</span>
            )}
          </div>
        </div>

        {/* From the posting — the jd_parsed extras, finally visible */}
        {hasPosting && (
          <Section title="From the posting">
            <div className="flex flex-col gap-3 rounded-frame border border-line bg-base p-4">
              {jd?.summary && (
                <p className="text-[13px] leading-relaxed text-ink-soft">{jd.summary}</p>
              )}
              {(jd?.salary || jd?.location) && (
                <div className="flex flex-wrap gap-x-6 gap-y-2.5">
                  {jd?.salary && <MicroFact label="Compensation" value={jd.salary} />}
                  {jd?.location && <MicroFact label="Location" value={jd.location} />}
                </div>
              )}
              {(jd?.key_requirements?.length ?? 0) > 0 && (
                <div>
                  <FactLabel>Key requirements</FactLabel>
                  <ul className="flex flex-col gap-1.5">
                    {jd!.key_requirements!.map((r, i) => (
                      <li
                        key={i}
                        className="relative pl-[18px] text-[12.5px] leading-snug text-ink-soft before:absolute before:left-[3px] before:top-2 before:size-[5px] before:rounded-full before:bg-accent/60"
                      >
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <path d="M12 2a7 7 0 0 0-7 7c0 3 2 5 3 7h8c1-2 3-4 3-7a7 7 0 0 0-7-7Z" />
                  <path d="M9 21h6" />
                </svg>
                Extracted by Claude when you pasted the posting
              </div>
            </div>
          </Section>
        )}

        {/* Notes */}
        {application.notes && (
          <Section title="Notes">
            <p className="text-[13px] leading-relaxed text-ink-soft">{application.notes}</p>
          </Section>
        )}

        {/* Tailored resume versions */}
        <Section title="Tailored resumes">
          {versions === null ? (
            <p className="text-[12px] text-ink-muted">Loading…</p>
          ) : versions.length === 0 ? (
            <p className="text-[12px] text-ink-muted">
              No tailored versions saved yet. Use{" "}
              <span className="text-ink-soft">Tailor resume</span> to draft one.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {versions.map((v) => (
                <div
                  key={v.id}
                  className="flex items-center gap-3 rounded-frame border border-line bg-base px-3 py-2.5"
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
                    <div className="text-[11px] text-ink-muted">Saved {fmt(v.created_at)}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => downloadVersion(v)}
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

      {/* Footer actions */}
      <div className="flex items-center justify-between gap-3 border-t border-line bg-surface px-6 py-3.5">
        <button
          type="button"
          onClick={() => onDelete(application)}
          className="rounded-interactive px-3 py-2 text-sm font-medium text-ink-muted transition-colors hover:border-[#4a2730] hover:text-[#f0a0a8]"
        >
          Delete
        </button>
        <div className="flex gap-2.5">
          <button
            type="button"
            onClick={() => onEdit(application)}
            className="rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={() => onTailor(application)}
            className="inline-flex items-center gap-2 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
            </svg>
            Tailor resume
          </button>
        </div>
      </div>
    </>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line-strong bg-surface-hover px-2.5 py-1 text-xs font-medium text-ink-soft">
      {children}
    </span>
  );
}

function FactLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-muted">
      {children}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <FactLabel>{label}</FactLabel>
      <div className="text-[13.5px] tabular-nums text-ink">{value}</div>
    </div>
  );
}

function MicroFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-[0.1em] text-ink-muted">{label}</span>
      <span className="text-[13px] text-ink">{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
        {title}
        <span className="h-px flex-1 bg-line" />
      </div>
      {children}
    </div>
  );
}
