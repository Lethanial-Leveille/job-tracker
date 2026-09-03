import { useState } from "react";
import type {
  Application,
  ApplicationStatus,
  ApplicationType,
  ParsedJob,
  RoleFamily,
} from "../../lib/types";
import { ROLE_FAMILIES } from "../../lib/types";
import { createApplication, parseJobDescription } from "../../lib/api";
import { statusLabel } from "../../lib/format";
import { findByOrganization, findSimilarPosting, findUrlMatch } from "../../lib/dedupe";

// The full-screen "Add an opportunity" flow that replaces the create modal.
// Three steps: Input (paste the posting) -> Parse (Claude reads it) -> Review
// (confirm the extracted fields, then save). Nothing is written until you hit
// Save on the Review step — hard rule #1, review before submit.

interface Props {
  onClose: () => void; // back to the list
  onSaved: () => void; // saved -> refetch + back to the list
  // Leave the add flow and open an existing row. Used by the duplicate notice,
  // so "you already have this" is a place you can go rather than a dead end.
  onOpenExisting: (id: string) => void;
  // The existing rows, for duplicate detection. Passed in rather than fetched
  // here: useApplications already holds the list, and checking against memory
  // is what makes the warning free and instant.
  applications: Application[];
}

type Step = "input" | "parse" | "review";
const ORDER: Step[] = ["input", "parse", "review"];

const STATUS_OPTIONS: ApplicationStatus[] = [
  "discovered",
  "drafting",
  "ready",
  "applied",
];

interface ReviewForm {
  type: ApplicationType;
  organization: string;
  role_or_program: string;
  role_family: RoleFamily;
  posting_url: string;
  status: ApplicationStatus;
  deadline: string;
  notes: string;
}

const BLANK: ReviewForm = {
  type: "internship",
  organization: "",
  role_or_program: "",
  // Fourteen of the first sixteen applications were this, so it is the honest
  // default for a row added by hand. The parser overwrites it on the paste path.
  role_family: "Software Engineer Intern",
  posting_url: "",
  status: "discovered",
  deadline: "",
  notes: "",
};

// Postings often carry no deadline ("rolling", "until filled"), and an empty
// deadline means the row sorts last and quietly falls off the bottom of the
// list. So default to a self-imposed one a week out. Local time, not UTC:
// toISOString() would roll the date backwards for anyone west of Greenwich,
// which is every evening here.
function defaultDeadline(): string {
  const d = new Date();
  d.setDate(d.getDate() + 7);
  const month = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

const labelClass =
  "flex flex-col gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-muted";
const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";

export function AddOpportunity({
  onClose,
  onSaved,
  onOpenExisting,
  applications,
}: Props) {
  const [step, setStep] = useState<Step>("input");
  const [pasteText, setPasteText] = useState("");
  // The posting link, now captured on the INPUT step rather than typed by hand
  // at review. Moving it earlier is the whole duplicate feature: with the link
  // in hand before the parse call, an already-tracked posting can be caught
  // before spending that call, instead of after.
  const [postingUrl, setPostingUrl] = useState("");
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsed, setParsed] = useState<ParsedJob | null>(null);
  const [form, setForm] = useState<ReviewForm>(() => ({
    ...BLANK,
    deadline: defaultDeadline(),
  }));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // The weaker post-parse match (same employer, similar title, different link).
  // Held in state rather than derived, because it can only be computed once the
  // parser has told us the organization and title.
  const [similar, setSimilar] = useState<Application | null>(null);
  // Others at the same employer, shown when the stronger checks find nothing.
  const [sameEmployer, setSameEmployer] = useState<Application[]>([]);

  // Derived, not state: recomputed each render straight from what you have
  // typed. There is nothing to keep in sync and nothing to invalidate.
  const urlDuplicate = findUrlMatch(applications, postingUrl);

  async function readWithProwl() {
    if (pasteText.trim() === "") return;
    setStep("parse");
    setParseError(null);
    try {
      const p = await parseJobDescription(pasteText);
      setParsed(p);
      setForm((f) => ({
        ...f,
        type: p.type,
        organization: p.organization,
        role_or_program: p.role_or_program,
        role_family: p.role_family,
        deadline: p.deadline ?? defaultDeadline(),
        // Carried from the input step so the link never gets typed twice. Still
        // editable at review.
        posting_url: postingUrl.trim(),
      }));
      // The second check, on employer + title. Catches the same job posted to
      // two boards, which the URL check cannot see. Skipped when the URL check
      // already matched, so you never get two warnings about one row.
      const match = urlDuplicate
        ? null
        : findSimilarPosting(applications, p.organization, p.role_or_program);
      setSimilar(match);
      // Only when nothing stronger fired, so one posting never produces two
      // notices about the same row.
      setSameEmployer(
        urlDuplicate || match ? [] : findByOrganization(applications, p.organization),
      );
      setStep("review");
    } catch (err: unknown) {
      setParseError(
        err instanceof Error ? err.message : "Could not read the posting",
      );
      setStep("input");
    }
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      await createApplication({
        type: form.type,
        organization: form.organization,
        role_or_program: form.role_or_program,
        posting_url: form.posting_url,
        status: form.status,
        role_family: form.role_family,
        deadline: form.deadline === "" ? null : form.deadline,
        notes: form.notes === "" ? null : form.notes,
        // Carry the parser's extras + the raw JD so the detail view can surface
        // them and tailoring can run against the real posting.
        jd_parsed: parsed
          ? {
              salary: parsed.salary,
              location: parsed.location,
              summary: parsed.summary,
              key_requirements: parsed.key_requirements,
            }
          : null,
        jd_text: pasteText.trim() === "" ? null : pasteText,
      });
      onSaved();
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Could not save");
      setSaving(false);
    }
  }

  const canSave =
    form.organization.trim() !== "" &&
    form.role_or_program.trim() !== "" &&
    form.posting_url.trim() !== "" &&
    !saving;

  function set<K extends keyof ReviewForm>(key: K, value: ReviewForm[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  return (
    <div className="relative">
      {/* Top bar: back + stepper */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center border-b border-line pb-5">
        <button
          type="button"
          onClick={onClose}
          className="inline-flex w-fit items-center gap-2 rounded-interactive border border-line bg-surface px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="m15 18-6-6 6-6" />
          </svg>
          Applications
        </button>
        <Stepper step={step} />
        <span />
      </div>

      <div className="mx-auto max-w-[720px] px-2 pb-20 pt-12">
        {step === "input" && (
          <div className="flex flex-col">
            <h1 className="text-balance text-center font-serif text-[42px] font-semibold tracking-[-0.01em] text-ink">
              Add an opportunity
            </h1>
            <p className="mx-auto mt-3.5 max-w-[460px] text-balance text-center text-[15px] leading-relaxed text-ink-soft">
              Paste a job description, or drop a link. Prowl reads
              it and fills in the details for you.
            </p>

            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              rows={11}
              placeholder="Paste the full job description here…"
              className="mt-9 min-h-[280px] w-full resize-y rounded-[14px] border border-line-strong bg-surface/60 px-6 py-5 text-sm leading-relaxed text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
            />

            <div className="my-6 flex items-center gap-4 text-[10.5px] uppercase tracking-[0.16em] text-ink-muted">
              <span className="h-px flex-1 bg-line" />
              Or paste a URL
              <span className="h-px flex-1 bg-line" />
            </div>

            {/* The link. This field used to be disabled behind a "URL reading is
                coming soon" promise; it now does real work. Prowl still does not
                FETCH the page (most job sites block that), but having the link
                before the parse call is what lets an already-tracked posting be
                caught for free, and it saves retyping the URL at review. */}
            <div className="relative">
              <svg className="pointer-events-none absolute left-4 top-1/2 size-[17px] -translate-y-1/2 text-ink-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" />
                <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />
              </svg>
              <input
                type="url"
                value={postingUrl}
                onChange={(e) => setPostingUrl(e.target.value)}
                placeholder="https://careers.example.com/role/12345"
                className="w-full rounded-xl border border-line-strong bg-surface/40 py-4 pl-11 pr-4 text-sm text-ink placeholder:text-ink-muted/70 focus:border-accent focus:shadow-glow focus:outline-none"
              />
            </div>

            {urlDuplicate ? (
              <DuplicateNotice
                application={urlDuplicate}
                heading="You're already tracking this posting"
                detail="Same link as a row you already have."
                onOpen={onOpenExisting}
              />
            ) : (
              <p className="ml-1 mt-1.5 flex items-center gap-1.5 text-[11px] text-ink-muted">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="9" />
                  <path d="M12 8h.01M11 12h1v4h1" />
                </svg>
                Prowl checks this against what you're already tracking before
                reading anything.
              </p>
            )}

            {parseError && (
              <p className="mt-4 rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink">
                {parseError}
              </p>
            )}

            <button
              type="button"
              onClick={readWithProwl}
              disabled={pasteText.trim() === ""}
              className="mt-6 flex w-full items-center justify-center gap-2.5 rounded-xl border border-line-strong bg-surface-hover py-[18px] text-[15px] font-medium text-ink transition-colors hover:border-accent-line disabled:opacity-50"
            >
              <svg className="size-[17px] text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M13 2 3 14h7l-1 8 10-12h-7z" />
              </svg>
              {urlDuplicate ? "Read it anyway" : "Read with Prowl"}
            </button>
            <p className="mt-4 text-center text-[12.5px] text-ink-muted">
              You'll review everything before it's saved.
            </p>
          </div>
        )}

        {step === "parse" && (
          <div className="flex flex-col items-center pt-16 text-center">
            <div className="mb-6 size-[66px] animate-spin rounded-full border-2 border-line-strong border-t-accent shadow-glow motion-reduce:animate-none" />
            <h2 className="font-serif text-[26px] font-semibold text-ink">
              Reading the posting
            </h2>
            <p className="mt-2 text-sm text-ink-soft">
              Prowl is pulling out the role, deadline, and key details…
            </p>
          </div>
        )}

        {step === "review" && (
          <div>
            <div className="mb-8 text-center">
              <h2 className="font-serif text-[30px] font-semibold text-ink">
                Review before saving
              </h2>
              <p className="mt-2 text-sm text-ink-soft">
                Prowl filled these in. Check them, fix anything, then save.
                Nothing is stored until you do.
              </p>
            </div>

            {similar && (
              <div className="mb-6">
                <DuplicateNotice
                  application={similar}
                  heading="This looks like one you already have"
                  detail="Same employer and a nearly identical title, under a different link."
                  onOpen={onOpenExisting}
                />
              </div>
            )}

            {sameEmployer.length > 0 && (
              <div className="mb-6 rounded-frame border border-line bg-surface px-4 py-3">
                <div className="text-[12.5px] text-ink-soft">
                  You already track{" "}
                  <span className="text-ink">
                    {sameEmployer.length}{" "}
                    {sameEmployer.length === 1 ? "application" : "applications"}
                  </span>{" "}
                  at {form.organization}. Not necessarily a duplicate — check it
                  is not the same one.
                </div>
                <ul className="mt-2 flex flex-col gap-1">
                  {sameEmployer.map((app) => (
                    <li key={app.id} className="flex items-center gap-2 text-[12px]">
                      <button
                        type="button"
                        onClick={() => onOpenExisting(app.id)}
                        className="truncate text-left text-ink-soft underline decoration-line underline-offset-2 transition-colors hover:text-ink"
                      >
                        {app.role_or_program}
                      </button>
                      <span className="shrink-0 text-ink-muted">
                        {statusLabel(app.status)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-4">
                <label className={labelClass}>
                  Organization
                  <input
                    value={form.organization}
                    onChange={(e) => set("organization", e.target.value)}
                    className={fieldClass}
                  />
                </label>
                <label className={labelClass}>
                  Type
                  <select
                    value={form.type}
                    onChange={(e) => set("type", e.target.value as ApplicationType)}
                    className={fieldClass}
                  >
                    <option value="internship">Job</option>
                      </select>
                </label>
              </div>

              <label className={labelClass}>
                Role or program
                <input
                  value={form.role_or_program}
                  onChange={(e) => set("role_or_program", e.target.value)}
                  className={fieldClass}
                />
              </label>

              <label className={labelClass}>
                Posting URL
                <input
                  value={form.posting_url}
                  onChange={(e) => set("posting_url", e.target.value)}
                  type="url"
                  placeholder="Add the link you applied through"
                  className={fieldClass}
                />
              </label>

              <div className="grid grid-cols-3 gap-4">
                <label className={labelClass}>
                  Status
                  <select
                    value={form.status}
                    onChange={(e) => set("status", e.target.value as ApplicationStatus)}
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
                    value={form.role_family}
                    onChange={(e) => set("role_family", e.target.value as RoleFamily)}
                    className={fieldClass}
                  >
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
                    value={form.deadline}
                    onChange={(e) => set("deadline", e.target.value)}
                    type="date"
                    className={fieldClass}
                  />
                </label>
              </div>

              {/* Captured extras — stored in jd_parsed, shown later in detail */}
              {parsed && (
                <div className="flex flex-col gap-2.5 rounded-frame border border-accent-line bg-accent-subtle px-4 py-3.5">
                  <div className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-accent">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                    Captured from the posting — stored and shown in the detail view
                  </div>
                  <div className="flex flex-wrap gap-x-6 gap-y-2">
                    {parsed.salary && <MiniKV label="Compensation" value={parsed.salary} />}
                    {parsed.location && <MiniKV label="Location" value={parsed.location} />}
                    {parsed.key_requirements.length > 0 && (
                      <MiniKV
                        label="Requirements"
                        value={`${parsed.key_requirements.length} captured`}
                      />
                    )}
                  </div>
                </div>
              )}

              {saveError && (
                <p className="rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink">
                  {saveError}
                </p>
              )}

              <div className="mt-2 flex items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => setStep("input")}
                  className="rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={save}
                  disabled={!canSave}
                  className="rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover disabled:opacity-60"
                >
                  {saving ? "Saving…" : "Save application"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stepper({ step }: { step: Step }) {
  const idx = ORDER.indexOf(step);
  const labels: Record<Step, string> = { input: "Input", parse: "Parse", review: "Review" };
  return (
    <div className="flex items-center gap-3.5">
      {ORDER.map((s, i) => (
        <div key={s} className="flex items-center gap-3.5">
          {i > 0 && (
            <span className={`h-px w-[46px] ${i <= idx ? "bg-accent-line" : "bg-line-strong"}`} />
          )}
          <span
            className={`inline-flex items-center gap-2.5 text-[13.5px] font-medium ${
              i === idx ? "text-ink" : i < idx ? "text-ink-soft" : "text-ink-muted"
            }`}
          >
            <span
              className={`grid size-[26px] place-items-center rounded-full border text-xs tabular-nums ${
                i === idx
                  ? "border-accent text-ink shadow-glow"
                  : i < idx
                    ? "border-accent bg-accent text-ink"
                    : "border-line-strong bg-surface text-ink-muted"
              }`}
            >
              {i + 1}
            </span>
            {labels[s]}
          </span>
        </div>
      ))}
    </div>
  );
}

function MiniKV({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-[0.1em] text-ink-muted">{label}</span>
      <span className="text-[13px] text-ink">{value}</span>
    </div>
  );
}

// Shown when the posting you're adding matches something already tracked. It is
// deliberately NOT a blocker: reapplying next cycle, or to a second team at the
// same company, is a real thing to do. It states what it found, offers the
// existing row, and otherwise stays out of the way.
//
// Neutral greys, no purple: per docs/design.md the accent is reserved for the
// primary action, selection, focus, and an offer. A warning is not on that list.
function DuplicateNotice({
  application,
  heading,
  detail,
  onOpen,
}: {
  application: Application;
  heading: string;
  detail: string;
  onOpen: (id: string) => void;
}) {
  const added = new Date(application.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <div className="mt-4 flex items-start gap-3.5 rounded-frame border border-line-strong bg-surface px-4 py-3.5">
      <svg
        className="mt-0.5 size-[18px] shrink-0 text-ink-soft"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5M12 16h.01" />
      </svg>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium text-ink">{heading}</div>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-soft">{detail}</p>
        <div className="mt-2 truncate text-[12.5px] text-ink-soft">
          <span className="text-ink">{application.organization}</span>
          {" — "}
          {application.role_or_program}
        </div>
        <div className="mt-0.5 text-[11.5px] text-ink-muted">
          Added {added} · {statusLabel(application.status)}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onOpen(application.id)}
        className="shrink-0 rounded-interactive border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
      >
        Open it
      </button>
    </div>
  );
}
