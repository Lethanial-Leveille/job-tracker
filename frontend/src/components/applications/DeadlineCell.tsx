import { daysSince, formatDeadline, shortDate } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";
import type { Application } from "../../lib/types";

// One column, three meanings, decided by where the row is.
//
// The rule: a posting deadline is only actionable while you have NOT applied.
// The moment it goes out the door the date stops being a thing to act on, so
// rather than blanking the column (which wastes it) or leaving a dead date
// (which is noise on 41 of 64 rows), it switches to the question that replaces
// it — how long have I been waiting.
//
// Urgency is carried by BRIGHTNESS, never hue. design.md allows one accent and
// spends it elsewhere, so there is no red here and no amber.
//
// Takes the whole application rather than a date because which of the three
// branches applies is a property of the row, not of the deadline.

// Inside four days is "act on this now". Wider than the old three-day "soon"
// because the column is now the primary urgency signal rather than a chip.
const URGENT_DAYS = 4;
// Three weeks of silence is the point where a follow-up is worth sending, so it
// is the point where the counter starts drawing the eye.
const QUIET_DAYS = 21;

export function DeadlineCell({ application }: { application: Application }) {
  // 1. Closed. Nothing to wait for and nothing to act on.
  if (isClosed(application.status)) {
    return <span className="text-sm tabular-nums text-ink-muted">—</span>;
  }

  // 2. Out the door. Count silence instead of a deadline.
  if (!isPreSubmit(application.status)) {
    if (!application.applied_at) {
      // Status says submitted but no `applied` event exists — a row imported
      // straight into a later stage. Nothing honest to count from.
      return <span className="text-sm tabular-nums text-ink-muted">—</span>;
    }
    const quiet = daysSince(application.applied_at);
    return (
      <div className="flex items-baseline gap-1.5 whitespace-nowrap">
        <span className="text-sm tabular-nums text-ink-soft">
          Sent {shortDate(application.applied_at)}
        </span>
        <span
          className={`text-[11px] tabular-nums ${
            quiet >= QUIET_DAYS ? "text-ink" : "text-ink-muted"
          }`}
        >
          quiet {quiet}d
        </span>
      </div>
    );
  }

  // 3. Still open. The deadline is the whole point of the row.
  const d = formatDeadline(application.deadline);
  if (!d) {
    return <span className="text-sm tabular-nums text-ink-muted">—</span>;
  }
  const urgent = d.days <= URGENT_DAYS;
  return (
    <div className="flex items-baseline gap-1.5 whitespace-nowrap">
      <span className={`text-sm tabular-nums ${urgent ? "text-ink" : "text-ink-soft"}`}>
        {d.date}
      </span>
      <span className={`text-[11px] ${urgent ? "text-ink-soft" : "text-ink-muted"}`}>
        {d.relative}
      </span>
    </div>
  );
}
