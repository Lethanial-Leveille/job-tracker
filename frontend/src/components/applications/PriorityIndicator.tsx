import type { Priority } from "../../lib/types";
import { priorityLabel } from "../../lib/format";

// Three ascending bars, low/medium/high lighting 1/2/3 of them. Grey only —
// priority is important but it is not the offer, so it stays out of the accent.
const LIT: Record<Priority, number> = { low: 1, medium: 2, high: 3 };
const BAR_HEIGHTS = [5, 8, 11]; // px, ascending

export function PriorityIndicator({ priority }: { priority: Priority }) {
  const lit = LIT[priority];

  return (
    <span className="inline-flex items-center gap-2 text-xs font-medium text-ink-soft">
      <svg width="14" height="12" viewBox="0 0 14 12" aria-hidden="true">
        {BAR_HEIGHTS.map((h, i) => (
          <rect
            key={i}
            x={i * 5}
            y={12 - h}
            width="3"
            height={h}
            rx="1"
            className={i < lit ? "fill-ink-soft" : "fill-line-strong"}
          />
        ))}
      </svg>
      {priorityLabel(priority)}
    </span>
  );
}
