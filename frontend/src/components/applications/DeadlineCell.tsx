import { formatDeadline } from "../../lib/format";

// Absolute date on top, a small relative chip below ("Tomorrow", "in 3 days").
// Overdue draws the eye by going brighter/near-white rather than by adopting a
// new color — the design keeps a single accent, so there is no red here.
export function DeadlineCell({ deadline }: { deadline: string | null }) {
  const d = formatDeadline(deadline);

  if (!d) {
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
