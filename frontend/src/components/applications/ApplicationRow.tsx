import type { Application } from "../../lib/types";
import { monogram } from "../../lib/format";
import { ROW_GRID } from "./grid";
import { StatusBadge } from "./StatusBadge";
import { TypeBadge } from "./TypeBadge";
import { PriorityIndicator } from "./PriorityIndicator";
import { DeadlineCell } from "./DeadlineCell";

interface Props {
  application: Application;
  selected: boolean;
  onSelect: (id: string) => void;
}

// One table row. Selecting a row is a legitimate use of the accent: the active
// row gets a purple left bar, a faint purple fill, and the soft glow. Every
// other row stays calm and only lifts to a grey surface on hover, so the data
// reads first and the purple means "this is the one you're on".
export function ApplicationRow({ application, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      onClick={() => onSelect(application.id)}
      className={`${ROW_GRID} w-full border-l-2 px-5 py-3.5 text-left transition-colors ${
        selected
          ? "border-l-accent bg-accent-subtle shadow-glow"
          : "border-l-transparent hover:bg-surface-hover"
      }`}
    >
      {/* Organization: monogram avatar + name */}
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-interactive border border-line bg-surface text-xs font-semibold text-ink-soft">
          {monogram(application.organization)}
        </span>
        <span className="truncate text-sm font-semibold text-ink">
          {application.organization}
        </span>
      </div>

      {/* Role or program */}
      <span className="truncate text-sm text-ink-soft">
        {application.role_or_program}
      </span>

      {/* Type */}
      <TypeBadge type={application.type} />

      {/* Status */}
      <div>
        <StatusBadge status={application.status} />
      </div>

      {/* Priority */}
      <PriorityIndicator priority={application.priority} />

      {/* Deadline */}
      <DeadlineCell deadline={application.deadline} />
    </button>
  );
}
