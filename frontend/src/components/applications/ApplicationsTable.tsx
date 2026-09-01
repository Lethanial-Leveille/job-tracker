import type { Application } from "../../lib/types";
import { ROW_GRID } from "./grid";
import { ApplicationRow } from "./ApplicationRow";

interface Props {
  applications: Application[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const COLUMNS = ["Organization", "Role", "Status", "Deadline"];

// The table container is a structural frame: crisp rounding, a real border, a
// dark surface. The header row is muted uppercase labels — chrome, not data.
// Rows carry the actual information and stay high contrast.
export function ApplicationsTable({ applications, selectedId, onSelect }: Props) {
  return (
    <div className="overflow-hidden rounded-frame border border-line-strong bg-surface">
      {/* Column header */}
      <div
        className={`${ROW_GRID} border-b border-line px-5 py-3 text-[11px] font-medium uppercase tracking-wider text-ink-muted`}
      >
        {COLUMNS.map((label) => (
          <span key={label}>{label}</span>
        ))}
        {/* Trailing actions column (open-posting link + chevron): no label. */}
        <span aria-hidden="true" />
      </div>

      {/* Rows */}
      <div className="divide-y divide-line">
        {applications.map((application) => (
          <ApplicationRow
            key={application.id}
            application={application}
            selected={application.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </div>
    </div>
  );
}
