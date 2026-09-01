import { useState } from "react";
import type { ChangeEvent, SyntheticEvent } from "react";
import type {
  Application,
  ApplicationStatus,
  ApplicationType,
  RoleFamily,
} from "../../lib/types";
import { ROLE_FAMILIES } from "../../lib/types";
import { statusLabel } from "../../lib/format";
import { deleteApplication, updateApplication } from "../../lib/api";

// The edit modal for an existing application. Creating is handled by the
// full-screen Add flow (AddOpportunity), so this is edit-only: `application` is
// required, and it exposes Save / Delete / Tailor. Opened from the detail
// drawer's Edit button.
//
// onClose dismisses without saving; onSaved fires after a successful
// update/delete (the parent refreshes the list and closes).

interface Props {
  application: Application;
  onClose: () => void;
  onSaved: () => void;
  // Open the tailoring flow for this saved application. The parent swaps this
  // modal for the TailorPanel (a saved id is required to save a version against).
  onTailor?: (application: Application) => void;
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
  // "" means the row has no family yet (created before classification existed).
  // Kept as a distinct empty option rather than defaulted, so opening an old row
  // to edit one field cannot silently assign it a family Lee never chose.
  role_family: RoleFamily | "";
  posting_url: string;
  status: ApplicationStatus;
  deadline: string; // "" means no deadline
  notes: string;
}

// Seed the form from the row being edited. The API sends deadline/notes as
// string | null; the form wants plain strings, so null becomes "".
function formFromApplication(app: Application): FormState {
  return {
    type: app.type,
    organization: app.organization,
    role_or_program: app.role_or_program,
    role_family: app.role_family ?? "",
    posting_url: app.posting_url,
    status: app.status,
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


const labelClass =
  "flex flex-col gap-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-muted";
const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";

export function ApplicationFormModal({
  application,
  onClose,
  onSaved,
  onTailor,
}: Props) {
  // Seed from the row. The initializer runs once, and the parent unmounts and
  // remounts this modal per row, so switching which row is edited works.
  const [form, setForm] = useState<FormState>(formFromApplication(application));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleChange(
    event: ChangeEvent<
      HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
    >,
  ) {
    const { name, value } = event.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(event: SyntheticEvent) {
    event.preventDefault();

    // Copy every field, then translate empty date/notes to null (the backend
    // wants null for "not set", and rejects "" as a date). Edit never touches
    // jd_parsed — the stored blob is left as it is.
    const payload = {
      ...form,
      deadline: form.deadline === "" ? null : form.deadline,
      notes: form.notes === "" ? null : form.notes,
      // "" is the form's "not set"; the API wants null. Sending "" would fail
      // the RoleFamily literal and 422 the whole save.
      role_family: form.role_family === "" ? null : form.role_family,
    };

    setSaving(true);
    setError(null);
    try {
      await updateApplication(application.id, payload);
      onSaved();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  async function handleDelete() {
    // Hard delete with no undo, so confirm before destroying the row.
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
          <h2 className="text-lg font-semibold text-ink">Edit application</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-interactive px-2 py-1 text-lg leading-none text-ink-muted transition-colors hover:text-ink"
          >
            ✕
          </button>
        </div>

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
              Role family
              <select
                name="role_family"
                value={form.role_family}
                onChange={handleChange}
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

          {/* Footer: Delete + Tailor on the left, Cancel + Save on the right. */}
          <div className="mt-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleDelete}
                disabled={saving}
                className="rounded-interactive px-3 py-2 text-sm font-medium text-ink-muted transition-colors hover:text-ink disabled:opacity-50"
              >
                Delete
              </button>
              {onTailor && (
                <button
                  type="button"
                  onClick={() => onTailor(application)}
                  disabled={saving}
                  className="rounded-interactive border border-line px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:text-ink disabled:opacity-50"
                >
                  Tailor resume
                </button>
              )}
            </div>

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
                {saving ? "Saving…" : "Save changes"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
