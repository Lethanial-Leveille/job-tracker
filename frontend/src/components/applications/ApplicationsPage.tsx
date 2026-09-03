import { useMemo, useState } from "react";
import type { Application } from "../../lib/types";
import type { ApplicationsState } from "../../lib/useApplications";
import { deleteApplication } from "../../lib/api";
import { ApplicationsTable } from "./ApplicationsTable";
import {
  ApplicationsToolbar,
  matchesStatusFilter,
  type StatusFilter,
} from "./ApplicationsToolbar";
import { ApplicationDetailPage } from "./ApplicationDetailPage";
import { AddOpportunity } from "./AddOpportunity";

// Deadline ascending with nulls last.
function byDeadline(a: Application, b: Application): number {
  if (a.deadline === b.deadline) return 0;
  if (a.deadline === null) return 1;
  if (b.deadline === null) return -1;
  return a.deadline < b.deadline ? -1 : 1;
}

// The command-center screen. It is a three-way view swap, not a stack: you are
// looking at the list, at one application, or at the add flow. Never at one on
// top of another.
//
// This replaced an arrangement of two stacked drawers plus a modal, where
// closing the tailor panel dropped you onto the detail panel rather than the
// list, and the edit modal opened over both. One layer means Back has exactly
// one meaning everywhere.
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

  const [adding, setAdding] = useState(false); // full-screen add view
  const [selectedId, setSelectedId] = useState<string | null>(null); // detail view

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = applications.filter((app) => {
      if (query) {
        const haystack = `${app.organization} ${app.role_or_program}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return matchesStatusFilter(app.status, statusFilter);
    });
    // Deadline order, always. Sorting by priority went away with the priority
    // field, and nothing else competes with "what is due next".
    return [...filtered].sort(byDeadline);
  }, [applications, statusFilter, search]);

  // Resolve the selected row from the live list so it stays fresh after a
  // refetch. A row deleted out from under us resolves to null, which falls
  // through to the list.
  const selected = applications.find((a) => a.id === selectedId) ?? null;

  async function handleDelete(app: Application) {
    if (!window.confirm("Delete this application? This cannot be undone.")) return;
    await deleteApplication(app.id);
    setSelectedId(null);
    refetch();
  }

  // The Add flow replaces the list entirely (sidebar stays).
  if (adding) {
    return (
      <AddOpportunity
        applications={applications}
        onClose={() => setAdding(false)}
        onSaved={() => {
          refetch();
          setAdding(false);
        }}
        // Leaving the add flow straight into the row you already had, so a
        // duplicate warning ends somewhere useful.
        onOpenExisting={(id) => {
          setAdding(false);
          setSelectedId(id);
        }}
      />
    );
  }

  // One application, also full screen.
  if (selected) {
    return (
      // key by id so moving between applications rebuilds the page from
      // scratch. Without it React reuses the instance, and the Overview tab's
      // form state (seeded once from props) would keep showing the previous
      // row's values.
      <ApplicationDetailPage
        key={selected.id}
        application={selected}
        onBack={() => setSelectedId(null)}
        onSaved={refetch}
        onDelete={handleDelete}
        onStatusChange={setStatus}
      />
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight text-ink">
              Applications
            </h1>
            <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium tabular-nums text-ink-soft">
              {visible.length} shown
            </span>
          </div>
          <p className="mt-1.5 text-sm text-ink-muted">
            Every internship you're tracking, in one pipeline.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search organization or role"
            className="w-64 rounded-interactive border border-line bg-surface px-3.5 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
          />
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-2 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover active:bg-accent-press"
          >
            <span className="text-base leading-none">+</span>
            New application
          </button>
        </div>
      </header>

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
        <StatePanel>Loading applications…</StatePanel>
      ) : error ? (
        <StatePanel>Could not load applications: {error}</StatePanel>
      ) : visible.length === 0 ? (
        <StatePanel>
          {applications.length === 0
            ? "No applications yet. Add your first one to start the pipeline."
            : "No applications match this filter."}
        </StatePanel>
      ) : (
        <ApplicationsTable
          applications={visible}
          selectedId={selectedId}
          onSelect={(id) => setSelectedId(id)}
          onStatusChange={setStatus}
          grouped={grouped}
        />
      )}
    </div>
  );
}

function StatePanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-frame border border-line-strong bg-surface px-6 py-16 text-center text-sm text-ink-muted">
      {children}
    </div>
  );
}
