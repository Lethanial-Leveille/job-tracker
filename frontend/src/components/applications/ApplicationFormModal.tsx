import { useState } from "react";
import type { ChangeEvent, SyntheticEvent } from "react";
import type {
  Application,
  ApplicationStatus,
  ApplicationType,
  ParsedJob,
  Priority,
} from "../../lib/types";
import { priorityLabel, statusLabel } from "../../lib/format";
import {
  createApplication,
  deleteApplication,
  parseJobDescription,
  updateApplication,
} from "../../lib/api";

// One modal for both creating and editing an application, because the form is
// identical either way. The `application` prop is the mode switch: absent means
// create, present means edit (and unlocks the Delete button). Keeping this as a
// single component means the eight fields are defined once, not twice.
//
// The parent renders it only when it wants it open. onClose dismisses without
// saving; onSaved fires after a successful create/update/delete (the parent
// refreshes the list and closes).

interface Props {
  application?: Application;
  onClose: () => void;
  onSaved: () => void;
}

// --- Form state -------------------------------------------------------------
// One object holds every field. Mirrors the payload we send, except the enum
// fields carry a valid default and deadline/notes are plain strings ("" meaning
// empty); we translate "" to null when building the payload. Typing it
// explicitly keeps the <select> values narrowed to the enum unions.

interface FormState {
  type: ApplicationType;
  organization: string;
  role_or_program: string;
  posting_url: string;
  status: ApplicationStatus;
  priority: Priority;
  deadline: string; // "" means no deadline
  notes: string;
}

const INITIAL_FORM: FormState = {
  type: "internship",
  organization: "",
  role_or_program: "",
  posting_url: "",
  status: "discovered",
  priority: "medium",
  deadline: "",
  notes: "",
};

// Seed the form from an existing row when editing. The API sends deadline/notes
// as string | null; the form wants plain strings, so null becomes "".
function formFromApplication(app: Application): FormState {
  return {
    type: app.type,
    organization: app.organization,
    role_or_program: app.role_or_program,
    posting_url: app.posting_url,
    status: app.status,
    priority: app.priority,
    deadline: app.deadline ?? "",
    notes: app.notes ?? "",
  };
}

// Runtime lists for the dropdowns. Mirror the enums in
// backend/models/application.py — keep in sync if the backend enums change.
const STATUS_OPTIONS: ApplicationStatus[] = [
  "discovered",
  "drafting",
  "ready",
  "applied",
  "recruiter_engaged",
  "phone_screen",
  "technical_interview",
  "onsite",
  "offer",
  "accepted",
  "declined",
  "rejected",
  "ghosted",
  "missed_deadline",
];

const PRIORITY_OPTIONS: Priority[] = ["low", "medium", "high"];

const labelClass =
  "flex flex-col gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted";
const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";

export function ApplicationFormModal({ application, onClose, onSaved }: Props) {
  // Seed from the row when editing, blank when creating. The initializer runs
  // once, so switching which row is edited works because the parent unmounts
  // and remounts this modal per row.
  const [form, setForm] = useState<FormState>(
    application ? formFromApplication(application) : INITIAL_FORM,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Autofill state (create mode only): the pasted posting, plus its own
  // loading/error, kept separate from the save flow so a parse failure never
  // looks like a save failure.
  const [pasteText, setPasteText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  // The parser's extras, stashed on autofill and sent with the create so they
  // land in the jd_parsed column. Null for a manual (non-autofilled) create.
  const [jdParsed, setJdParsed] = useState<Record<string, unknown> | null>(
    null,
  );

  function handleChange(
    event: ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  // Merge Claude's extraction into the form. Only the four fields ParsedJob maps
  // to a column are filled; posting_url stays for you to add (you pasted text,
  // not a URL). deadline null becomes "" to match the form's string fields. The
  // extras (salary, summary, requirements) aren't persisted yet — that's the
  // jd_parsed follow-up.
  function applyParsed(parsed: ParsedJob) {
    setForm((prev) => ({
      ...prev,
      type: parsed.type,
      organization: parsed.organization,
      role_or_program: parsed.role_or_program,
      deadline: parsed.deadline ?? "",
    }));
    // Stash the fields with no column of their own for the jd_parsed blob.
    setJdParsed({
      salary: parsed.salary,
      location: parsed.location,
      summary: parsed.summary,
      key_requirements: parsed.key_requirements,
    });
  }

  async function handleAutofill() {
    if (pasteText.trim() === "") return;
    setParsing(true);
    setParseError(null);
    try {
      applyParsed(await parseJobDescription(pasteText));
    } catch (err: unknown) {
      setParseError(
        err instanceof Error ? err.message : "Could not parse the posting",
      );
    } finally {
      setParsing(false);
    }
  }

  async function handleSubmit(event: SyntheticEvent) {
    event.preventDefault();

    // Copy every field, then translate empty date/notes to null (the backend
    // wants null for "not set", and rejects "" as a date).
    const payload = {
      ...form,
      deadline: form.deadline === "" ? null : form.deadline,
      notes: form.notes === "" ? null : form.notes,
    };

    setSaving(true);
    setError(null);
    try {
      // The presence of `application` picks POST vs PATCH. Checking the object
      // itself (not a boolean) is what lets TypeScript know id exists here.
      if (application) {
        // Edit never touches jd_parsed — leave the stored blob as it is.
        await updateApplication(application.id, payload);
      } else {
        // Create carries the parser's extras (null if you didn't autofill).
        await createApplication({ ...payload, jd_parsed: jdParsed });
      }
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!application) return;
    // Hard delete with no undo in v1, so confirm before destroying the row.
    if (!window.confirm("Delete this application? This cannot be undone.")) {
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await deleteApplication(application.id);
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not delete");
      setSaving(false);
    }
  }

  const isEdit = application !== undefined;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-frame border border-line-strong bg-surface p-6 shadow-2xl"
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-ink">
            {isEdit ? "Edit application" : "New application"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-interactive px-2 py-1 text-lg leading-none text-ink-muted transition-colors hover:text-ink"
          >
            ✕
          </button>
        </div>

        {/* Autofill: create mode only. Paste a posting, Claude fills the fields
            below, you review and save. Secondary (grey) action — purple stays
            reserved for Save. */}
        {!isEdit && (
          <div className="mt-6 rounded-frame border border-line bg-base p-4">
            <label className={labelClass}>
              Autofill from a posting
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                rows={4}
                placeholder="Paste the job or scholarship description here…"
                className={`${fieldClass} resize-none`}
              />
            </label>
            {parseError && (
              <p className="mt-2 rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink">
                {parseError}
              </p>
            )}
            <div className="mt-3 flex items-center justify-between gap-3">
              <span className="text-xs text-ink-muted">
                Claude fills the fields below. Review before saving.
              </span>
              <button
                type="button"
                onClick={handleAutofill}
                disabled={parsing || pasteText.trim() === ""}
                className="rounded-interactive border border-line px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
              >
                {parsing ? "Parsing…" : "Autofill"}
              </button>
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4">
          <label className={labelClass}>
            Organization
            <input
              name="organization"
              value={form.organization}
              onChange={handleChange}
              required
              placeholder="e.g. Knight-Hennessy"
              className={fieldClass}
            />
          </label>

          <label className={labelClass}>
            Role or program
            <input
              name="role_or_program"
              value={form.role_or_program}
              onChange={handleChange}
              required
              placeholder="e.g. Graduate Fellowship"
              className={fieldClass}
            />
          </label>

          <label className={labelClass}>
            Posting URL
            <input
              name="posting_url"
              type="url"
              value={form.posting_url}
              onChange={handleChange}
              required
              placeholder="https://…"
              className={fieldClass}
            />
          </label>

          <div className="grid grid-cols-2 gap-4">
            <label className={labelClass}>
              Type
              <select
                name="type"
                value={form.type}
                onChange={handleChange}
                className={fieldClass}
              >
                <option value="internship">Job</option>
                <option value="scholarship">Scholarship</option>
              </select>
            </label>

            <label className={labelClass}>
              Status
              <select
                name="status"
                value={form.status}
                onChange={handleChange}
                className={fieldClass}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </label>

            <label className={labelClass}>
              Priority
              <select
                name="priority"
                value={form.priority}
                onChange={handleChange}
                className={fieldClass}
              >
                {PRIORITY_OPTIONS.map((p) => (
                  <option key={p} value={p}>
                    {priorityLabel(p)}
                  </option>
                ))}
              </select>
            </label>

            <label className={labelClass}>
              Deadline
              <input
                name="deadline"
                type="date"
                value={form.deadline}
                onChange={handleChange}
                className={fieldClass}
              />
            </label>
          </div>

          <label className={labelClass}>
            Notes
            <textarea
              name="notes"
              value={form.notes}
              onChange={handleChange}
              rows={3}
              placeholder="Anything worth remembering"
              className={`${fieldClass} resize-none`}
            />
          </label>

          {error && (
            <p className="rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink">
              {error}
            </p>
          )}

          {/* Footer: Delete on the left (edit mode only), Cancel + Save on the
              right. justify-between pushes them apart; the empty span keeps Save
              right-aligned in create mode when there is no Delete. */}
          <div className="mt-2 flex items-center justify-between gap-3">
            {isEdit ? (
              <button
                type="button"
                onClick={handleDelete}
                disabled={saving}
                className="rounded-interactive px-3 py-2 text-sm font-medium text-ink-muted transition-colors hover:text-ink disabled:opacity-50"
              >
                Delete
              </button>
            ) : (
              <span />
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={onClose}
                disabled={saving}
                className="rounded-interactive border border-line px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover active:bg-accent-press disabled:opacity-60"
              >
                {saving
                  ? "Saving…"
                  : isEdit
                    ? "Save changes"
                    : "Save application"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
