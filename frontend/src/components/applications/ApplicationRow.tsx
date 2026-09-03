import type { KeyboardEvent } from "react";
import type { Application, ApplicationStatus } from "../../lib/types";
import { monogram } from "../../lib/format";
import { ROW_GRID } from "./grid";
import { StatusSelect } from "./StatusSelect";
import { DeadlineCell } from "./DeadlineCell";

interface Props {
  application: Application;
  selected: boolean;
  onSelect: (id: string) => void;
  onStatusChange: (id: string, status: ApplicationStatus) => void;
}

// One table row. The whole row opens the detail drawer, so it acts as a button
// (role + keyboard handling). It is a <div>, not a <button>, because it hosts
// two further independent controls: the open-posting link and the status menu.
// Neither a link nor a select can legally nest inside a button, so the row is a
// clickable container and each inner control stops its own events from also
// opening the drawer.
export function ApplicationRow({
  application,
  selected,
  onSelect,
  onStatusChange,
}: Props) {
  const open = () => onSelect(application.id);

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      open();
    }
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={onKeyDown}
      aria-label={`Open ${application.organization} — ${application.role_or_program}`}
      className={`${ROW_GRID} group w-full cursor-pointer border-l-2 px-5 py-3.5 text-left transition-colors focus:outline-none focus-visible:bg-surface-hover ${
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

      {/* Role: the normalized family, so the column scans cleanly. Rows added
          before classification existed have none, so fall back to the posted
          title rather than showing an empty cell. */}
      <span className="truncate text-sm text-ink-soft">
        {application.role_family ?? application.role_or_program}
      </span>

      {/* Status: editable in place, so marking something Applied never means
          opening the row and the edit form. */}
      <div>
        <StatusSelect
          application={application}
          onChange={onStatusChange}
          chevronOnHover
        />
      </div>

      {/* Deadline */}
      <DeadlineCell deadline={application.deadline} />

      {/* Actions: open the posting (independent link) + a detail affordance. */}
      <div className="flex items-center justify-end gap-0.5">
        {application.posting_url && (
          <a
            href={application.posting_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            aria-label={`Open ${application.organization} posting in a new tab`}
            className="grid size-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-surface hover:text-ink focus-visible:text-ink"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M14 4h6v6M20 4l-8 8" />
              <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" />
            </svg>
          </a>
        )}
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
          className="text-ink-muted/50 transition-colors group-hover:text-ink-muted"
        >
          <path d="m9 6 6 6-6 6" />
        </svg>
      </div>
    </div>
  );
}
