import type { Application, ApplicationStatus } from "../../lib/types";
import { monogram } from "../../lib/format";
import { ROW_GRID } from "./grid";
import { ApplicationRow } from "./ApplicationRow";
import { groupByOrganization } from "./grouping";

interface Props {
  applications: Application[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onStatusChange: (id: string, status: ApplicationStatus) => void;
  // Break the rows into per-employer sections. Off by default: the flat list is
  // sorted by deadline, and that ordering answers the question the list exists
  // to answer.
  grouped?: boolean;
}

// The first column changes meaning when grouped: the employer heading carries
// the company, so the rows beneath it carry the posted title instead.
const COLUMNS = ["Organization", "Role", "Status", "Deadline"];
const GROUPED_COLUMNS = ["Position", "Role", "Status", "Deadline"];

// The table container is a structural frame: crisp rounding, a real border, a
// dark surface. The header row is muted uppercase labels — chrome, not data.
// Rows carry the actual information and stay high contrast.
export function ApplicationsTable({
  applications,
  selectedId,
  onSelect,
  onStatusChange,
  grouped,
}: Props) {
  const renderRow = (application: Application) => (
    <ApplicationRow
      key={application.id}
      application={application}
      selected={application.id === selectedId}
      onSelect={onSelect}
      onStatusChange={onStatusChange}
      grouped={grouped}
    />
  );

  return (
    <div className="overflow-hidden rounded-frame border border-line-strong bg-surface">
      {/* Column header */}
      <div
        className={`${ROW_GRID} border-b border-line px-5 py-3 text-[11px] font-medium uppercase tracking-wider text-ink-muted`}
      >
        {(grouped ? GROUPED_COLUMNS : COLUMNS).map((label) => (
          <span key={label}>{label}</span>
        ))}
        {/* Trailing actions column (open-posting link + chevron): no label. */}
        <span aria-hidden="true" />
      </div>

      {/* Rows, flat or in per-employer sections. */}
      {grouped ? (
        <div>
          {groupByOrganization(applications).map((group) => (
            <div key={group.key}>
              <div className="flex items-center gap-2.5 border-y border-line bg-base px-5 py-2.5">
                <span className="grid size-6 shrink-0 place-items-center rounded-md border border-line bg-surface text-[10px] font-semibold text-ink-soft">
                  {monogram(group.label)}
                </span>
                <span className="truncate text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-soft">
                  {group.label}
                </span>
                <span className="rounded-full border border-line px-1.5 text-[10px] tabular-nums text-ink-muted">
                  {group.applications.length}
                </span>
              </div>
              <div className="divide-y divide-line">
                {group.applications.map(renderRow)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="divide-y divide-line">{applications.map(renderRow)}</div>
      )}
    </div>
  );
}
