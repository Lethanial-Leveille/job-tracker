import type { Application, ApplicationStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";
import { StatusBadge } from "./StatusBadge";
import { menuStatuses } from "./statuses";

// The status cell, made editable in place. Click the badge, pick a value, done:
// two interactions instead of the five it used to take (open the row, click
// Edit, open the select, pick, save).
//
// It is a NATIVE <select> rendered at opacity-0 directly over the badge, rather
// than a hand-built popup menu. Two reasons, both concrete:
//
//   1. ApplicationsTable's container is `overflow-hidden` (it clips the corner
//      rounding of the first and last rows). An absolutely positioned menu
//      inside a row would be clipped by that. A native select is drawn by the
//      browser as an OS level popup and cannot be clipped.
//   2. It arrives with keyboard support, touch support, and screen reader
//      semantics already correct. A custom menu means rebuilding all of it.
//
// The cost is that the option list itself can't be styled. Fine here: the
// options are plain words, and the closed state — the part actually on screen —
// is still our own StatusBadge.

interface Props {
  application: Application;
  onChange: (id: string, status: ApplicationStatus) => void;
  // Hide the chevron until the surrounding `group` is hovered. The table passes
  // this so a resting list of twenty rows doesn't sprout twenty chevrons. On
  // its own (the detail page header) there is no `group` ancestor to hover, so
  // the default is a chevron that is simply always visible.
  chevronOnHover?: boolean;
}

export function StatusSelect({ application, onChange, chevronOnHover }: Props) {
  return (
    // Both handlers stop the event reaching the row. The row is a role="button"
    // that opens the detail view on click AND on Enter/Space, so without these
    // every use of this menu would also open the drawer behind it.
    <div
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      className="relative inline-flex w-fit items-center gap-1 rounded-full focus-within:shadow-glow focus-within:outline focus-within:outline-1 focus-within:outline-accent"
    >
      <StatusBadge status={application.status} />

      {/* The affordance. */}
      <svg
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        className={`shrink-0 transition-colors ${
          chevronOnHover
            ? "text-transparent group-hover:text-ink-muted"
            : "text-ink-muted"
        }`}
      >
        <path d="m6 9 6 6 6-6" />
      </svg>

      <select
        value={application.status}
        onChange={(e) => onChange(application.id, e.target.value as ApplicationStatus)}
        aria-label={`Status for ${application.organization}`}
        className="absolute inset-0 cursor-pointer opacity-0"
      >
        {menuStatuses(application.status).map((status) => (
          <option key={status} value={status}>
            {statusLabel(status)}
          </option>
        ))}
      </select>
    </div>
  );
}
