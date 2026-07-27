// The frame each resume section sits in: a titled card with an optional "Add"
// action in its header (used by the repeatable sections — Education, Experience,
// Projects, Skills — to append a new entry). Contact has no Add, so onAdd is
// optional. Keeps section chrome consistent and out of the section components.
//
// Styling follows the design system's "drama in the frame": a line-strong border
// on surface, greys only — the accent stays reserved for the shell's Save action.

import type { ReactNode } from "react";

interface Props {
  title: string;
  description?: string;
  onAdd?: () => void;
  addLabel?: string;
  children: ReactNode;
}

export function SectionCard({
  title,
  description,
  onAdd,
  addLabel = "Add",
  children,
}: Props) {
  return (
    <section className="rounded-frame border border-line-strong bg-surface p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {description && (
            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted">
              {description}
            </p>
          )}
        </div>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="shrink-0 rounded-interactive border border-line bg-base px-3 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
          >
            + {addLabel}
          </button>
        )}
      </div>
      <div className="mt-4 flex flex-col gap-4">{children}</div>
    </section>
  );
}

// One repeatable entry inside a SectionCard (a single school, job, project, or
// skill group): a bordered block with a small remove control in its header. The
// repeatable sections render one per array item.
export function EntryBlock({
  label,
  onRemove,
  children,
}: {
  label: string;
  onRemove: () => void;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-interactive border border-line bg-base p-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
          {label}
        </span>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${label}`}
          className="grid size-7 place-items-center rounded-interactive text-ink-muted transition-colors hover:text-ink"
        >
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>
      {children}
    </div>
  );
}

// Muted placeholder shown when a repeatable section has no entries yet.
export function EmptyHint({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-ink-muted">{children}</p>;
}
