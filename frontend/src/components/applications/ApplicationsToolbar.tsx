import type { ApplicationStatus } from "../../lib/types";

// What the list can be narrowed to. The point of this control is the question
// Lee actually asks the list: "which of these have I already applied to?"
export type StatusFilter = "all" | "not_applied" | "applied";

// "Not applied" is the pre-submit set: found it, drafting for it, ready to send.
// Everything from `applied` onward means it went out the door, however it ended.
// `missed_deadline` is in NEITHER bucket on purpose — it was never applied to and
// it can never be applied to, so it would be noise in the actionable list. It is
// still reachable under "All".
const NOT_APPLIED: ApplicationStatus[] = ["discovered", "drafting", "ready"];

export function matchesStatusFilter(
  status: ApplicationStatus,
  filter: StatusFilter,
): boolean {
  if (filter === "all") return true;
  const isPreSubmit = NOT_APPLIED.includes(status);
  if (filter === "not_applied") return isPreSubmit;
  return !isPreSubmit && status !== "missed_deadline";
}

interface Props {
  statusFilter: StatusFilter;
  onStatusFilter: (value: StatusFilter) => void;
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

export function ApplicationsToolbar({ statusFilter, onStatusFilter }: Props) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Segmented
        options={STATUS_TABS}
        value={statusFilter}
        onChange={onStatusFilter}
      />
    </div>
  );
}
