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
  // Counts per tab, so the control says how much is behind each one rather than
  // making you click to find out. Computed by the caller, which already has the
  // list; passing it down avoids this component needing the data.
  counts: Record<StatusFilter, number>;
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
  counts,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  counts?: Record<string, number>;
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
          {counts && (
            <span className="ml-1.5 text-[10px] tabular-nums text-ink-spent">
              {counts[opt.value] ?? 0}
            </span>
          )}
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
  counts,
}: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4">
      <Segmented
        options={STATUS_TABS}
        value={statusFilter}
        onChange={onStatusFilter}
        counts={counts}
      />

      {/* Grouping is opt-in, not the default. The flat list is ordered by
          deadline, and grouping necessarily breaks that global ordering — so it
          is a thing you reach for when looking at one company, not the way the
          pipeline sits at rest. */}
      {/* A real switch rather than a button that looks pressed. Grouping is a
          persistent mode, and a mode wants a control that shows its state at
          rest — a toggled button only reads as on once you compare it to how it
          looked before. */}
      <button
        type="button"
        onClick={() => onGrouped(!grouped)}
        role="switch"
        aria-checked={grouped}
        className="inline-flex items-center gap-2.5 text-[12.5px] text-ink-3 transition-colors hover:text-ink"
      >
        <span
          className={`relative h-3 w-[22px] rounded-full transition-colors ${
            grouped ? "bg-accent-text" : "bg-stage-sent"
          }`}
        >
          <span
            className={`absolute top-0.5 size-2 rounded-full bg-base transition-all ${
              grouped ? "left-[12px]" : "left-0.5"
            }`}
          />
        </span>
        Group by company
      </button>
    </div>
  );
}
