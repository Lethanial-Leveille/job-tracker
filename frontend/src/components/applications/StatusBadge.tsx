import type { ApplicationStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";

// The one place purple is allowed to touch the data: an offer. Every other
// status is neutral grey, per the design rule. "discovered" (our earliest
// state) reads as "not started" with a hollow dot; everything in flight gets a
// filled dot. Nothing here competes with the offer's purple.
export function StatusBadge({ status }: { status: ApplicationStatus }) {
  const label = statusLabel(status);

  if (status === "offer") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-accent px-2.5 py-1 text-xs font-medium text-ink">
        <span className="size-1.5 rounded-full bg-ink" />
        {label}
      </span>
    );
  }

  const dormant = status === "discovered";

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink-soft">
      {dormant ? (
        <span className="size-1.5 rounded-full border border-ink-muted" />
      ) : (
        <span className="size-1.5 rounded-full bg-ink-soft" />
      )}
      {label}
    </span>
  );
}
