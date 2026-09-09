import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { Application } from "../../lib/types";
import type { ApplicationsState } from "../../lib/useApplications";
import { ApplicationsTable } from "./ApplicationsTable";
import {
  ApplicationsToolbar,
  matchesStatusFilter,
  type StatusFilter,
} from "./ApplicationsToolbar";
import { CommandPalette } from "./CommandPalette";
import { StatsStrip } from "./StatsStrip";
import { SuggestionsPanel } from "./SuggestionsPanel";
import { SAVED_VIEWS, findView } from "./views";
import { useListKeyboard } from "./useListKeyboard";

// Deadline ascending with nulls last.
function byDeadline(a: Application, b: Application): number {
  if (a.deadline === b.deadline) return 0;
  if (a.deadline === null) return 1;
  if (b.deadline === null) return -1;
  return a.deadline < b.deadline ? -1 : 1;
}

// The pipeline list.
//
// This used to BE the detail page and the add flow as well, swapping between
// the three on local state. They are routes now (see App.tsx): the swap gave
// the browser no history to go back through, so Back left the app entirely, and
// a refresh always landed you here no matter where you had been. Opening a row
// is a navigation now, which is why this component is only the list again.
export function ApplicationsPage({
  applications,
  loading,
  error,
  refetch,
  setStatus,
  saveError,
  dismissSaveError,
}: ApplicationsState) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [search, setSearch] = useState("");
  const [grouped, setGrouped] = useState(false);

  const navigate = useNavigate();
  // The active saved view lives in the URL, so the sidebar can be plain links
  // and a filtered list is a real address you can come back to.
  const [searchParams] = useSearchParams();
  const activeView = findView(searchParams.get("view"));

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = applications.filter((app) => {
      if (query) {
        const haystack = `${app.organization} ${app.role_or_program}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      // A saved view narrows on top of the status tabs rather than replacing
      // them, so "In process" + "Applied" is a legal (if redundant) combination
      // instead of one control silently overriding the other.
      if (activeView && !activeView.matches(app)) return false;
      return matchesStatusFilter(app.status, statusFilter);
    });
    // Deadline order, always. Sorting by priority went away with the priority
    // field, and nothing else competes with "what is due next".
    return [...filtered].sort(byDeadline);
  }, [applications, statusFilter, search, activeView]);

  // ⌘K. Registered here rather than inside the palette so the palette can stay
  // a pure presentational component that is simply absent when closed.
  const [paletteOpen, setPaletteOpen] = useState(false);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const keyboard = useListKeyboard({
    applications: visible,
    onOpen: (id) => navigate(`/applications/${id}`),
    onStatusChange: setStatus,
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        {/* No count pill and no tagline. The sidebar already carries the count,
            and a tool its only user opens every day does not need to explain on
            every screen what it is for. Both were the same information a third
            and fourth time. */}
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Applications
          </h1>
          {activeView && (
            <button
              type="button"
              onClick={() => navigate("/applications")}
              className="mt-1 inline-flex items-center gap-1.5 text-[12px] text-ink-muted transition-colors hover:text-ink"
            >
              {activeView.label}
              <span aria-hidden="true">×</span>
              <span className="sr-only">Clear this view</span>
            </button>
          )}
        </div>

        <div className="flex w-full items-center gap-3 sm:w-auto">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search organization or role"
            className="min-w-0 flex-1 rounded-interactive border border-line bg-surface px-3.5 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none sm:w-64 sm:flex-none"
          />
          <button
            type="button"
            onClick={() => navigate("/applications/new")}
            className="inline-flex items-center gap-2 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink transition-shadow transition-colors hover:bg-accent-hover hover:shadow-glow active:bg-accent-press"
          >
            <span className="text-base leading-none">+</span>
            New application
          </button>
        </div>
      </header>

      <StatsStrip applications={applications} />

      <SuggestionsPanel applications={applications} onResolved={refetch} />

      <ApplicationsToolbar
        statusFilter={statusFilter}
        onStatusFilter={setStatusFilter}
        grouped={grouped}
        onGrouped={setGrouped}
      />

      {/* A failed write, not a failed load: the table below is still correct, so
          this is a banner over a working list rather than a replacement for it. */}
      {saveError && (
        <div className="flex items-center justify-between gap-4 rounded-frame border border-line-strong bg-surface px-4 py-3 text-sm text-ink">
          <span>{saveError}</span>
          <button
            type="button"
            onClick={dismissSaveError}
            className="shrink-0 rounded-interactive px-2 py-1 text-xs font-medium text-ink-muted transition-colors hover:text-ink"
          >
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        // A skeleton, not the word "Loading". The table's shape is known before
        // the data arrives, so drawing it keeps the page from jumping when rows
        // land and tells you what is coming.
        <TableSkeleton />
      ) : error ? (
        <StatePanel>
          <p className="text-ink">Could not load applications.</p>
          <p className="mt-1 text-ink-muted">{error}</p>
          <button
            type="button"
            onClick={refetch}
            className="mt-4 rounded-interactive border border-line-ctrl bg-surface px-3.5 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
          >
            Try again
          </button>
        </StatePanel>
      ) : visible.length === 0 ? (
        // Three different nothings, which want three different messages: an
        // empty account, a filter that matched nothing, and a search that did.
        // "No applications match this filter" while you are staring at a search
        // box you just typed into is the app failing to notice what you did.
        <StatePanel>
          {applications.length === 0 ? (
            <>
              <p className="text-ink">No applications yet.</p>
              <p className="mt-1 text-ink-muted">
                Paste a posting and Prowl fills in the rest.
              </p>
              <button
                type="button"
                onClick={() => navigate("/applications/new")}
                className="mt-4 rounded-interactive bg-accent px-3.5 py-1.5 text-[13px] font-medium text-ink transition-colors hover:bg-accent-hover"
              >
                Add your first application
              </button>
            </>
          ) : search.trim() !== "" ? (
            <>
              <p className="text-ink">Nothing matches “{search.trim()}”.</p>
              <button
                type="button"
                onClick={() => setSearch("")}
                className="mt-3 text-[13px] text-ink-muted transition-colors hover:text-ink"
              >
                Clear search
              </button>
            </>
          ) : (
            <>
              <p className="text-ink">Nothing here right now.</p>
              <p className="mt-1 text-ink-muted">
                {activeView
                  ? `No applications are in “${activeView.label}”.`
                  : "No applications match this filter."}
              </p>
            </>
          )}
        </StatePanel>
      ) : (
        <ApplicationsTable
          applications={visible}
          selectedId={keyboard.selectedId}
          onSelect={(id) => navigate(`/applications/${id}`)}
          onStatusChange={setStatus}
          grouped={grouped}
        />
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        applications={applications}
        onOpenApplication={(id) => navigate(`/applications/${id}`)}
        commands={[
          {
            id: "new",
            label: "New application",
            hint: "N",
            run: () => navigate("/applications/new"),
          },
          {
            id: "resume",
            label: "Go to Resume",
            run: () => navigate("/resume"),
          },
          {
            id: "general",
            label: "General resume",
            run: () => navigate("/resume/base"),
          },
          {
            id: "group",
            label: grouped ? "Ungroup by company" : "Group by company",
            run: () => setGrouped((v) => !v),
          },
          ...(activeView
            ? [
                {
                  id: "clear-view",
                  label: `Clear view: ${activeView.label}`,
                  run: () => navigate("/applications"),
                },
              ]
            : SAVED_VIEWS.map((v) => ({
                id: `view-${v.key}`,
                label: `View: ${v.label}`,
                run: () => navigate(`/applications?view=${v.key}`),
              }))),
        ]}
      />

      {/* The keyboard footer, shipped only now that every shortcut it advertises
          actually works — a legend for keys that do nothing is worse than no
          legend. ⇧S is deliberately absent; see useListKeyboard. */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-3 text-[11px] tabular-nums text-ink-muted">
        <span>
          <b className="font-medium text-ink-soft">j</b>/<b className="font-medium text-ink-soft">k</b> move
          {" · "}
          <b className="font-medium text-ink-soft">⏎</b> open
          {" · "}
          <b className="font-medium text-ink-soft">e</b> mark applied
          {" · "}
          <b className="font-medium text-ink-soft">⌘Z</b> undo
        </span>
        <span>
          {visible.length} shown of {applications.length}
        </span>
      </div>

      {/* Undo, not confirm. Marking applied fires immediately: a dialog on an
          action taken forty times a morning costs more than the mistake it
          prevents. Fixed so it is reachable wherever you are in the list. */}
      {keyboard.lastChange && (
        <div className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-frame border border-line-strong bg-surface px-4 py-2.5 text-[13px] text-ink shadow-lg">
          <span>
            Marked <span className="font-medium">{keyboard.lastChange.organization}</span> as
            applied
          </span>
          <button
            type="button"
            onClick={keyboard.undo}
            className="rounded-interactive border border-line px-2.5 py-1 text-[12px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
          >
            Undo
          </button>
          <button
            type="button"
            onClick={keyboard.dismissUndo}
            aria-label="Dismiss"
            className="text-ink-muted transition-colors hover:text-ink"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}

function StatePanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-frame border border-line-strong bg-surface px-6 py-16 text-center text-sm text-ink-muted">
      <div>{children}</div>
    </div>
  );
}

// Eight rows at the real row height, so the page does not resize when data
// lands. Animation is a pulse on the bars only: the frame stays still, because
// a whole table breathing reads as broken rather than loading.
function TableSkeleton() {
  return (
    <div className="rounded-frame border border-line-strong bg-surface">
      <div className="border-b border-line px-4 py-2">
        <div className="h-2 w-24 rounded bg-line-ctrl" />
      </div>
      <div className="divide-y divide-line-row">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 px-4 py-[7px]">
            <div className="h-2.5 flex-1 animate-pulse rounded bg-line-ctrl motion-reduce:animate-none" />
            <div className="h-2.5 w-28 animate-pulse rounded bg-line motion-reduce:animate-none" />
            <div className="h-2.5 w-20 animate-pulse rounded bg-line motion-reduce:animate-none" />
          </div>
        ))}
      </div>
    </div>
  );
}
