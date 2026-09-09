import { formatDeadline } from "../../lib/format";
import { isSubmitted } from "./statuses";
import type { ApplicationStatus } from "../../lib/types";

// Absolute date on top, a small relative chip below ("Tomorrow", "in 3 days").
// Overdue draws the eye by going brighter/near-white rather than by adopting a
// new color — the design keeps a single accent, so there is no red here.
export function DeadlineCell({
  deadline,
  status,
}: {
  deadline: string | null;
  status: ApplicationStatus;
}) {
  const d = formatDeadline(deadline);

  // A deadline on a row that is already out the door is noise: there is nothing
  // left to do by that date, whether it has passed or not. Same reasoning as the
  // SUBMITTED set in scripts/backfill_deadlines.py, and it matters because these
  // dates are mostly SELF-IMPOSED apply-by dates rather than posted ones — once
  // you have applied, the date recorded nothing about the posting.
  //
  // `missed_deadline` is deliberately NOT in that set and keeps its date: there
  // the passed deadline is the whole story, not noise.
  //
  // Display only. The column still sorts on the real value, and the date is
  // still in the database and on the detail page.
  if (!d || isSubmitted(status)) {
    return <span className="text-sm text-ink-muted">—</span>;
  }

  const overdue = d.urgency === "overdue";

  // ONE line, not two. Stacking the date over a bordered chip made this the
  // tallest cell in the table, so a single component set the height of every
  // row — the whole reason the list read as airy against a design doc asking
  // for "dense and data forward". The chip is now a plain muted suffix.
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className="text-sm tabular-nums text-ink">{d.date}</span>
      <span className={`text-[11px] ${overdue ? "text-ink" : "text-ink-muted"}`}>
        {d.relative}
      </span>
    </div>
  );
}
