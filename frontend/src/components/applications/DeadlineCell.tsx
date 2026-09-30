import { useRef } from "react";
import { compactRelative, daysSince, formatDeadline, shortDate } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";
import type { Application } from "../../lib/types";
import type { DateField } from "../../lib/useApplications";

// One column, four meanings, decided by where the row is.
//
// The rule: a posting deadline is only actionable while you have NOT applied.
// The moment it goes out the door the date stops being a thing to act on, so
// rather than blanking the column (which wastes it) or leaving a dead date
// (which is noise on 41 of 64 rows), it switches to the question that replaces
// it — how long have I been waiting. Unless the ball is back in your court: an
// assessment or other stage task with a due date (`next_step_due`) replaces the
// silence counter, because "due in 4d" is the thing to act on.
//
// Urgency is carried by BRIGHTNESS, never hue. design.md allows one accent and
// spends it elsewhere, so there is no red here and no amber.
//
// Takes the whole application rather than a date because which of the four
// branches applies is a property of the row, not of the deadline.

// Inside four days is "act on this now". Wider than the old three-day "soon"
// because the column is now the primary urgency signal rather than a chip.
const URGENT_DAYS = 4;
// Three weeks of silence is the point where a follow-up is worth sending, so it
// is the point where the counter starts drawing the eye.
const QUIET_DAYS = 21;

// The secondary text truncates rather than overflowing: the column is a fixed
// width, and an overflow runs under the posting-link icon beside it.
const ROW = "flex min-w-0 items-baseline gap-1.5 whitespace-nowrap";
const SUB = "truncate text-[11px]";

interface Props {
  application: Application;
  // Optional so the cell can still render read only (its tests do). When set,
  // clicking the cell opens a date picker for whichever date it is showing.
  onDateChange?: (field: DateField, value: string | null) => void;
}

// Which date a click edits follows the same branches as the display below: the
// posting's deadline while you have not applied, the stage's due date once you
// have. A closed row has nothing worth dating, so it stays plain text.
function editableField(application: Application): DateField | null {
  if (isClosed(application.status)) return null;
  return isPreSubmit(application.status) ? "deadline" : "next_step_due";
}

export function DeadlineCell({ application, onDateChange }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const field = editableField(application);
  if (!onDateChange || !field) return <DeadlineText application={application} />;

  function openPicker() {
    const input = inputRef.current;
    if (!input) return;
    // showPicker() is the only way to open a native date picker from a click
    // somewhere else. Older browsers lack it, so fall back to focusing the
    // input, which at least lets the keyboard type a date.
    try {
      input.showPicker();
    } catch {
      input.focus();
    }
  }

  return (
    // A real button, so it is reachable by Tab and Enter opens the picker. Both
    // events stop here for the same reason as StatusSelect's wrapper: the row
    // underneath is itself clickable and would open the drawer too.
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation();
        openPicker();
      }}
      onKeyDown={(e) => e.stopPropagation()}
      title={field === "deadline" ? "Set the deadline" : "Set when the next step is due"}
      className="relative -mx-1.5 min-w-0 rounded-md px-1.5 py-0.5 text-left transition-colors hover:bg-surface focus:outline-none focus-visible:bg-surface"
    >
      <DeadlineText application={application} />
      {/* The picker's anchor. Visually hidden rather than display:none, because
          a browser will not open a picker for an input that is not rendered.
          An empty value from the picker's Clear button means "no date". */}
      <input
        ref={inputRef}
        type="date"
        tabIndex={-1}
        aria-hidden="true"
        value={application[field] ?? ""}
        onChange={(e) => onDateChange(field, e.target.value || null)}
        onClick={(e) => e.stopPropagation()}
        className="pointer-events-none absolute bottom-0 left-0 h-px w-px opacity-0"
      />
    </button>
  );
}

function DeadlineText({ application }: { application: Application }) {
  // 1. Closed. Nothing to wait for and nothing to act on.
  if (isClosed(application.status)) {
    return <span className="text-sm tabular-nums text-ink-muted">—</span>;
  }

  if (!isPreSubmit(application.status)) {
    // 2. Out the door, but a stage task is waiting on you. Checked before the
    // applied_at guard: a row imported straight into Assessment has no
    // `applied` event, and its due date is still worth showing.
    const due = formatDeadline(application.next_step_due);
    if (due) {
      const urgent = due.days <= URGENT_DAYS;
      return (
        <div className={ROW}>
          <span className={`text-sm tabular-nums ${urgent ? "text-ink" : "text-ink-soft"}`}>
            Due {due.date}
          </span>
          <span className={`${SUB} tabular-nums ${urgent ? "text-ink-soft" : "text-ink-muted"}`}>
            {compactRelative(due.days)}
          </span>
        </div>
      );
    }

    // 3. Out the door and waiting. Count silence instead of a deadline.
    if (!application.applied_at) {
      // Status says submitted but no `applied` event exists — a row imported
      // straight into a later stage. Nothing honest to count from.
      return <span className="text-sm tabular-nums text-ink-muted">—</span>;
    }
    // Silence restarts at every status change: an assessment invite is them
    // replying. "Sent" stays the original submission, which dates the row.
    const quiet = daysSince(application.last_status_at ?? application.applied_at);
    return (
      <div className={ROW}>
        <span className="text-sm tabular-nums text-ink-soft">
          Sent {shortDate(application.applied_at)}
        </span>
        <span
          className={`${SUB} tabular-nums ${
            quiet >= QUIET_DAYS ? "text-ink" : "text-ink-muted"
          }`}
        >
          quiet {quiet}d
        </span>
      </div>
    );
  }

  // 4. Still open. The deadline is the whole point of the row.
  const d = formatDeadline(application.deadline);
  if (!d) {
    return <span className="text-sm tabular-nums text-ink-muted">—</span>;
  }
  // A date you set yourself is never urgent, however close it is. Nothing
  // closes on it, so brightening it would spend the column's one signal on a
  // reminder and leave a real closing date looking identical to a preference.
  // It still shows, because the reason it exists is to keep the row visible.
  const mine = application.deadline_source === "self";
  const urgent = !mine && d.days <= URGENT_DAYS;
  const relative = compactRelative(d.days);
  return (
    <div className={ROW}>
      <span
        className={`text-sm tabular-nums ${
          urgent ? "text-ink" : mine ? "text-ink-muted" : "text-ink-soft"
        }`}
      >
        {d.date}
      </span>
      <span className={`${SUB} ${urgent ? "text-ink-soft" : "text-ink-muted"}`}>
        {mine ? `yours · ${relative}` : relative}
      </span>
    </div>
  );
}
