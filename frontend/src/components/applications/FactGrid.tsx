import type { Application } from "../../lib/types";
import { daysSince, formatDeadline, shortDate, statusLabel } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";
import { gradDateHint } from "../../lib/gradHint";

// The facts about an application, as something you read rather than something
// you fill in.
//
// It replaces the top of a page that opened with six permanently-editable
// inputs. That form asked a question ("what would you like to change?") when the
// question actually being asked is "what is this, and where does it stand?" —
// and an input is the least scannable way to display a value it renders in a
// box, at form-field size, with a caret.
//
// Read-only on purpose. Editing still lives in the form below, one disclosure
// away. That is a smaller claim than click-to-edit and an honest one: the value
// here was never the editing, it was not having six boxes above the fold.

function Cell({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3">
      <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-label">
        {label}
      </span>
      <span className={`text-[13px] ${muted ? "text-ink-spent" : "text-ink-body"}`}>
        {value}
      </span>
    </div>
  );
}

// The deadline is shown here even when the LIST has retired it, and labelled
// "spent". The list hides it because it is not actionable; the record should
// still hold it, and this is the page where the record lives.
function deadlineFact(app: Application): { value: string; muted: boolean } {
  const d = formatDeadline(app.deadline);
  if (!d) return { value: "—", muted: true };
  if (isPreSubmit(app.status)) return { value: `${d.date} · ${d.relative}`, muted: false };
  return { value: `${d.date} · spent`, muted: true };
}

function statusFact(app: Application): string {
  const label = statusLabel(app.status);
  if (isClosed(app.status) || isPreSubmit(app.status)) return label;
  if (!app.applied_at) return label;
  return `${label} · sent ${shortDate(app.applied_at)} · quiet ${daysSince(app.applied_at)}d`;
}

function hint(app: Application) {
  return gradDateHint(app);
}

function gradFact(app: Application): string {
  const h = hint(app);
  if (!h) return "May 2028 · default";
  const date = h.suggest === "alternate" ? "May 2029" : "May 2028";
  return `${date} · ${h.basis === "standing" ? "from posting" : "inferred"}`;
}

export function FactGrid({ application }: { application: Application }) {
  const jd = application.jd_parsed as Record<string, unknown> | null;
  const salary = typeof jd?.salary === "string" ? jd.salary : null;
  const location = typeof jd?.location === "string" ? jd.location : null;
  const deadline = deadlineFact(application);

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-frame border border-line-frame bg-line-frame sm:grid-cols-2">
      <div className="bg-surface">
        <Cell label="Status" value={statusFact(application)} />
      </div>
      <div className="bg-surface">
        <Cell label="Deadline" value={deadline.value} muted={deadline.muted} />
      </div>
      <div className="bg-surface">
        <Cell
          label="Role family"
          value={application.role_family ?? "Not set"}
          muted={!application.role_family}
        />
      </div>
      <div className="bg-surface">
        <Cell label="Compensation" value={salary ?? "Not stated"} muted={!salary} />
      </div>
      <div className="bg-surface">
        <Cell label="Location" value={location ?? "Not stated"} muted={!location} />
      </div>
      <div className="bg-surface">
        {/* Surfaces the gradHint decision so it is visible on the record rather
            than only as a pre-ticked checkbox in the tailor tab. Which date
            PRINTS is still chosen per download; this says what the posting
            implies and why. */}
        <Cell label="Grad date" value={gradFact(application)} muted={!hint(application)} />
      </div>
    </div>
  );
}
