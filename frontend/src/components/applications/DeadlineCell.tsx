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

  return (
    <div className="flex flex-col gap-1">
      <span className="text-sm text-ink">{d.date}</span>
      <span
        className={`inline-flex w-fit rounded-full border border-line bg-surface px-1.5 py-0.5 text-[11px] ${
          overdue ? "text-ink" : "text-ink-muted"
        }`}
      >
        {d.relative}
      </span>
    </div>
  );
}
