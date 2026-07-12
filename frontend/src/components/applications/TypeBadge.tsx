import type { ApplicationType } from "../../lib/types";
import { typeLabel } from "../../lib/format";

// Neutral outlined pill. "internship" renders as "Job". Never purple — type is
// not a signal that earns the accent.
export function TypeBadge({ type }: { type: ApplicationType }) {
  return (
    <span className="inline-flex items-center rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink-soft">
      {typeLabel(type)}
    </span>
  );
}
