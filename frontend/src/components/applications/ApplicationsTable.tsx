import type { Application, ApplicationStatus } from "../../lib/types";
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
  // `underHeading` is per-row, not per-table: in the grouped view an employer
  // with a single application renders WITHOUT a heading, so that row must still
  // show the company name. Passing the table-wide `grouped` flag straight
  // through would blank the employer on exactly the rows nothing else names.
  const renderRow = (application: Application, underHeading = grouped) => (
    <ApplicationRow
      key={application.id}
      application={application}
      selected={application.id === selectedId}
      onSelect={onSelect}
      onStatusChange={onStatusChange}
      grouped={underHeading}
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
              {/* A heading over ONE row organises nothing: it just repeats the
                  employer above a row that would have said it anyway, and adds
                  a count of "1". Employers with a single application render as
                  an ordinary row instead, so the section headings that remain
                  all mean something — several roles at one company, which is
                  the only case grouping exists for. */}
              {group.applications.length > 1 && (
                <div className="flex items-center gap-2.5 border-y border-line bg-base px-5 py-2">
                  <span className="truncate text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-soft">
                    {group.label}
                  </span>
                  <span className="text-[10px] tabular-nums text-ink-muted">
                    {group.applications.length}
                  </span>
                </div>
              )}
              <div className="divide-y divide-line">
                {group.applications.map((a) =>
                  renderRow(a, group.applications.length > 1),
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // Called through an arrow, NOT passed to map directly: map hands the
        // array INDEX as its second argument, which would land in
        // `underHeading` and make every row after the first think it sits under
        // a heading, blanking the employer. tsc -b caught this; tsc --noEmit
        // did not.
        <div className="divide-y divide-line">
          {applications.map((a) => renderRow(a))}
        </div>
      )}
    </div>
  );
}
