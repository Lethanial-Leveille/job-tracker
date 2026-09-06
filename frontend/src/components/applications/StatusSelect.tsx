import type { Application, ApplicationStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";
import { Select } from "../ui/Select";
import { StatusBadge } from "./StatusBadge";
import { menuStatuses } from "./statuses";

// The status cell, editable in place. Click the badge, pick a value, done.
//
// This used to be a native <select> held at opacity-0 over the badge, chosen
// because it can't be clipped by the table's `overflow-hidden` and arrives with
// keyboard and screen reader behaviour for free. The cost was that the OPEN
// list was drawn by the operating system and could not be styled — a bright
// generic menu in the middle of a dark app.
//
// components/ui/Select answers both of those (a portal escapes the clipping, and
// the listbox keyboard behaviour is rebuilt), so the menu is finally ours. The
// closed state is unchanged: it is still our own StatusBadge.

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
  const options = menuStatuses(application.status).map((status) => ({
    value: status,
    label: statusLabel(status),
  }));

  return (
    // Both handlers stop the event reaching the row. The row is a role="button"
    // that opens the detail view on click AND on Enter/Space, so without these
    // every use of this menu would also open the detail page behind it.
    <div
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => e.stopPropagation()}
      className="inline-flex w-fit"
    >
      <Select
        value={application.status}
        options={options}
        onChange={(next) => onChange(application.id, next)}
        ariaLabel={`Status for ${application.organization}`}
        className="inline-flex w-fit cursor-pointer items-center gap-1 rounded-full outline-none focus-visible:shadow-glow focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent"
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
      </Select>
    </div>
  );
}
