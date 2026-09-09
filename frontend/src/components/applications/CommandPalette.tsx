import { useEffect, useMemo, useRef, useState } from "react";
import type { Application } from "../../lib/types";
import { statusLabel } from "../../lib/format";

// ⌘K: jump to any application by name, or run one of a short list of commands.
//
// Two design constraints it has to respect:
//
//   1. It must not fight the list's j/k handler. It does not need to negotiate:
//      that handler already ignores every keystroke while focus is in a field,
//      and ⌘K itself carries a modifier it bails on. The palette owns the
//      keyboard purely by having focus.
//   2. It only offers what exists. Every command here is something the app can
//      already do — no "Soon", no greyed-out rows. That is the same rule the
//      sidebar follows.
//
// Arrow keys move, ⏎ runs, Esc closes. Deliberately not a fuzzy matcher: over 64
// rows a plain substring match on organization and role is both predictable and
// correct, and predictability is worth more here than cleverness.

export interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  onClose: () => void;
  applications: Application[];
  onOpenApplication: (id: string) => void;
  commands: Command[];
}

export function CommandPalette({
  open,
  onClose,
  applications,
  onOpenApplication,
  commands,
}: Props) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Reopening should be a clean slate: a palette that remembers last night's
  // query is a palette you have to clear before you can use it.
  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      // Focus after paint, or the input is not in the document yet.
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matchedCommands = commands.filter((c) =>
      q === "" ? true : c.label.toLowerCase().includes(q),
    );
    const matchedApps =
      q === ""
        ? applications.slice(0, 5)
        : applications
            .filter((a) =>
              `${a.organization} ${a.role_or_program}`.toLowerCase().includes(q),
            )
            .slice(0, 8);
    return { matchedCommands, matchedApps, total: matchedCommands.length + matchedApps.length };
  }, [query, applications, commands]);

  if (!open) return null;

  function runAt(i: number) {
    if (i < results.matchedCommands.length) {
      results.matchedCommands[i].run();
    } else {
      const app = results.matchedApps[i - results.matchedCommands.length];
      if (app) onOpenApplication(app.id);
    }
    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 px-4 pt-[12vh]"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[520px] overflow-hidden rounded-frame border border-line-ctrl bg-overlay shadow-2xl"
      >
        <input
          ref={inputRef}
          value={query}
          placeholder="Search applications or run a command…"
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.preventDefault();
              onClose();
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndex((i) => Math.min(i + 1, Math.max(results.total - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              runAt(index);
            }
          }}
          className="w-full border-b border-line bg-transparent px-4 py-3 text-[14px] text-ink placeholder:text-ink-label focus:outline-none"
        />

        <div className="max-h-[52vh] overflow-y-auto py-1.5">
          {results.total === 0 && (
            <p className="px-4 py-6 text-center text-[13px] text-ink-muted">
              Nothing matches “{query.trim()}”.
            </p>
          )}

          {results.matchedCommands.length > 0 && (
            <Group label="Commands">
              {results.matchedCommands.map((c, i) => (
                <Row key={c.id} active={i === index} onSelect={() => runAt(i)}>
                  <span className="text-ink">{c.label}</span>
                  {c.hint && <span className="text-[11px] text-ink-label">{c.hint}</span>}
                </Row>
              ))}
            </Group>
          )}

          {results.matchedApps.length > 0 && (
            <Group label="Applications">
              {results.matchedApps.map((a, i) => {
                const at = results.matchedCommands.length + i;
                return (
                  <Row key={a.id} active={at === index} onSelect={() => runAt(at)}>
                    <span className="truncate text-ink">{a.organization}</span>
                    <span className="truncate text-[11px] text-ink-3">
                      {a.role_or_program} · {statusLabel(a.status)}
                    </span>
                  </Row>
                );
              })}
            </Group>
          )}
        </div>
      </div>
    </div>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="py-1">
      <div className="px-4 pb-1 text-[10px] font-medium uppercase tracking-[0.12em] text-ink-label">
        {label}
      </div>
      {children}
    </div>
  );
}

function Row({
  active,
  onSelect,
  children,
}: {
  active: boolean;
  onSelect: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      // onMouseDown, not onClick: the input has focus and a click would blur it
      // first, which closes nothing but does move focus mid-gesture.
      onMouseDown={(e) => {
        e.preventDefault();
        onSelect();
      }}
      className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-[13px] transition-colors ${
        active ? "bg-raised" : "hover:bg-surface-hover"
      }`}
    >
      {children}
    </button>
  );
}
