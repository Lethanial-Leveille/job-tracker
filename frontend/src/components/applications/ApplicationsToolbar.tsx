import type { ApplicationStatus } from "../../lib/types";
import { isPreSubmit } from "./statuses";

// What the list can be narrowed to. The point of this control is the question
// Lee actually asks the list: "which of these have I already applied to?"
export type StatusFilter = "all" | "not_applied" | "applied";

// `missed_deadline` is in NEITHER bucket on purpose — it was never applied to
// and it can never be applied to, so it would be noise in the actionable list.
// It is still reachable under "All".
export function matchesStatusFilter(
  status: ApplicationStatus,
  filter: StatusFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "not_applied") return isPreSubmit(status);
  return !isPreSubmit(status) && status !== "missed_deadline";
}

interface Props {
  statusFilter: StatusFilter;
  onStatusFilter: (value: StatusFilter) => void;
  grouped: boolean;
  onGrouped: (value: boolean) => void;
}

const STATUS_TABS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "not_applied", label: "Not applied" },
  { value: "applied", label: "Applied" },
];

// A small segmented control. The active segment is a grey lift, not purple —
// filtering is not on the accent's short list. These controls operate on real
// loaded data, so they genuinely work.
function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="inline-flex items-center gap-1 rounded-interactive border border-line bg-surface p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
            opt.value === value
              ? "bg-surface-hover text-ink"
              : "text-ink-muted hover:text-ink-soft"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function ApplicationsToolbar({
  statusFilter,
  onStatusFilter,
  grouped,
  onGrouped,
}: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <Segmented
        options={STATUS_TABS}
        value={statusFilter}
        onChange={onStatusFilter}
      />

      {/* Grouping is opt-in, not the default. The flat list is ordered by
          deadline, and grouping necessarily breaks that global ordering — so it
          is a thing you reach for when looking at one company, not the way the
          pipeline sits at rest. */}
      <button
        type="button"
        onClick={() => onGrouped(!grouped)}
        aria-pressed={grouped}
        className={`inline-flex items-center gap-2 rounded-interactive border px-3 py-2 text-[13px] font-medium transition-colors ${
          grouped
            ? "border-line-strong bg-surface-hover text-ink"
            : "border-line bg-surface text-ink-muted hover:text-ink-soft"
        }`}
      >
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <path d="M4 6h16M7 12h13M7 18h13M4 12h.01M4 18h.01" />
        </svg>
        Group by company
      </button>
    </div>
  );
}
