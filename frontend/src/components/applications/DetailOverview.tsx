import { useState } from "react";
import type { Application, FitReport, RoleFamily } from "../../lib/types";
import { ROLE_FAMILIES } from "../../lib/types";
import { updateApplication } from "../../lib/api";
import { FitSection } from "./FitSection";

// The Overview tab: the application's own fields, editable in place, plus what
// the parser pulled out of the posting.
//
// This replaces ApplicationFormModal. The fields are always live rather than
// sitting behind an Edit button that opened a modal on top of a drawer — the
// modal existed only to hold inputs, and a full page has room for them. The
// save bar appears only once something actually differs, so the page reads as
// information until you change it, then admits it has unsaved work.

interface Props {
  application: Application;
  onSaved: () => void;
  onDelete: (application: Application) => void;
}

interface FormState {
  organization: string;
  role_or_program: string;
  posting_url: string;
  // "" means no family, for rows created before classification existed. Kept
  // distinct from a real value so opening an old row to fix its deadline can't
  // silently assign it a family you never chose.
  role_family: RoleFamily | "";
  deadline: string; // "" means no deadline
  notes: string;
}

function formFrom(app: Application): FormState {
  return {
    organization: app.organization,
    role_or_program: app.role_or_program,
    posting_url: app.posting_url,
    role_family: app.role_family ?? "",
    deadline: app.deadline ?? "",
    notes: app.notes ?? "",
  };
}

const labelClass =
  "flex flex-col gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-muted";
const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm font-normal normal-case tracking-normal text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function DetailOverview({ application, onSaved, onDelete }: Props) {
  const initial = formFrom(application);
  const [form, setForm] = useState<FormState>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Seeded from the row's cached report, then updated locally when you rerun the
  // check — the freshly returned report is the same object the server just
  // stored, so refetching the whole list to see it would be a wasted round trip.
  const [report, setReport] = useState<FitReport | null>(application.fit_report);

  // Compare against the row as it currently is, so the bar disappears by itself
  // after a save refreshes the parent, with no extra state to reset.
  const dirty = (Object.keys(initial) as (keyof FormState)[]).some(
    (key) => form[key] !== initial[key],
  );

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await updateApplication(application.id, {
        ...form,
        // The API wants null for "not set"; "" would fail validation on a date
        // and on the role family Literal.
        deadline: form.deadline === "" ? null : form.deadline,
        notes: form.notes === "" ? null : form.notes,
        role_family: form.role_family === "" ? null : form.role_family,
      });
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  const jd = application.jd_parsed;
  // Requirements are excluded here: they have their own section below, where
  // they can carry verdicts. This block is only the posting's loose extras.
  const hasPosting = Boolean(jd && (jd.summary || jd.salary || jd.location));

  return (
    <div className="flex flex-col gap-8 pb-24">
      <Section title="Details">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className={labelClass}>
            Organization
            <input
              value={form.organization}
              onChange={(e) => set("organization", e.target.value)}
              className={fieldClass}
            />
          </label>

          <label className={labelClass}>
            Role or program
            <input
              value={form.role_or_program}
              onChange={(e) => set("role_or_program", e.target.value)}
              className={fieldClass}
            />
          </label>

          <label className={labelClass}>
            Role family
            <select
              value={form.role_family}
              onChange={(e) => set("role_family", e.target.value as RoleFamily | "")}
              className={fieldClass}
            >
              <option value="">Not set</option>
              {ROLE_FAMILIES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>

          <label className={labelClass}>
            Deadline
            <input
              type="date"
              value={form.deadline}
              onChange={(e) => set("deadline", e.target.value)}
              className={fieldClass}
            />
          </label>

          <label className={`${labelClass} sm:col-span-2`}>
            Posting URL
            <input
              type="url"
              value={form.posting_url}
              onChange={(e) => set("posting_url", e.target.value)}
              className={fieldClass}
            />
          </label>

          <label className={`${labelClass} sm:col-span-2`}>
            Notes
            <textarea
              value={form.notes}
              onChange={(e) => set("notes", e.target.value)}
              rows={3}
              placeholder="Anything worth remembering"
              className={`${fieldClass} resize-none`}
            />
          </label>
        </div>

        <p className="text-[11.5px] text-ink-muted">
          Added {fmtDate(application.created_at)}
        </p>
      </Section>

      {hasPosting && (
        <Section title="From the posting">
          <div className="flex flex-col gap-3 rounded-frame border border-line bg-surface p-4">
            {jd?.summary && (
              <p className="text-[13px] leading-relaxed text-ink-soft">{jd.summary}</p>
            )}
            {(jd?.salary || jd?.location) && (
              <div className="flex flex-wrap gap-x-6 gap-y-2.5">
                {jd?.salary && <MicroFact label="Compensation" value={jd.salary} />}
                {jd?.location && <MicroFact label="Location" value={jd.location} />}
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

      <Section title="Requirements">
        <FitSection
          application={application}
          report={report}
          onComputed={setReport}
        />
      </Section>

      <div>
        <button
          type="button"
          onClick={() => onDelete(application)}
          className="rounded-interactive border border-line px-3 py-2 text-sm font-medium text-ink-muted transition-colors hover:border-[#4a2730] hover:text-[#f0a0a8]"
        >
          Delete application
        </button>
      </div>

      {/* The save bar. Fixed to the bottom of the viewport and present only
          while there are unsaved changes, so the page cannot be left in an
          ambiguous state without saying so. */}
      {(dirty || error) && (
        <div className="fixed inset-x-0 bottom-0 z-40 border-t border-line-strong bg-surface/95 backdrop-blur-sm">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3.5 sm:px-8">
            <span className="text-[13px] text-ink-soft">
              {error ?? "Unsaved changes"}
            </span>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={() => {
                  setForm(initial);
                  setError(null);
                }}
                disabled={saving}
                className="rounded-interactive border border-line px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
              >
                Discard
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving || !dirty}
                className="rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink transition-shadow transition-colors hover:bg-accent-hover hover:shadow-glow disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}
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
    <div className="flex flex-col gap-3.5">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
        {title}
        <span className="h-px flex-1 bg-line" />
      </div>
      {children}
    </div>
  );
}
