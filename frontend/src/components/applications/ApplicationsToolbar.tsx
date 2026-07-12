import type { ApplicationType } from "../../lib/types";

export type TypeFilter = "all" | ApplicationType;
export type SortKey = "deadline" | "priority";

interface Props {
  typeFilter: TypeFilter;
  onTypeFilter: (value: TypeFilter) => void;
  sort: SortKey;
  onSort: (value: SortKey) => void;
}

const TYPE_TABS: { value: TypeFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "internship", label: "Jobs" },
  { value: "scholarship", label: "Scholarships" },
];

const SORT_TABS: { value: SortKey; label: string }[] = [
  { value: "deadline", label: "Deadline" },
  { value: "priority", label: "Priority" },
];

// A small segmented control. The active segment is a grey lift, not purple —
// filtering and sorting are not on the accent's short list. These controls
// operate on real loaded data, so they genuinely work.
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
    <div className="inline-flex rounded-interactive border border-line bg-base p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            value === opt.value
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
  typeFilter,
  onTypeFilter,
  sort,
  onSort,
}: Props) {
  return (
    <div className="flex items-center justify-between gap-4">
      <Segmented
        options={TYPE_TABS}
        value={typeFilter}
        onChange={onTypeFilter}
      />
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-medium uppercase tracking-wider text-ink-muted">
          Sort
        </span>
        <Segmented options={SORT_TABS} value={sort} onChange={onSort} />
      </div>
    </div>
  );
}
