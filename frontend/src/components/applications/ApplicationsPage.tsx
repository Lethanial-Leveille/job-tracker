import { useMemo, useState } from "react";
import type { Application, Priority } from "../../lib/types";
import type { ApplicationsState } from "../../lib/useApplications";
import { ApplicationsTable } from "./ApplicationsTable";
import {
  ApplicationsToolbar,
  type SortKey,
  type TypeFilter,
} from "./ApplicationsToolbar";
import { ApplicationFormModal } from "./ApplicationFormModal";

const PRIORITY_RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

// Deadline ascending with nulls last: a row with no deadline sorts after every
// dated row rather than jumping to the top.
function byDeadline(a: Application, b: Application): number {
  if (a.deadline === b.deadline) return 0;
  if (a.deadline === null) return 1;
  if (b.deadline === null) return -1;
  return a.deadline < b.deadline ? -1 : 1;
}

// The command-center screen: it receives the loaded list from App, then
// filter/sort/select all happen client-side over it. This is the only screen
// wired to the API in v1 (GET /applications).
export function ApplicationsPage({
  applications,
  loading,
  error,
  refetch,
}: ApplicationsState) {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [sort, setSort] = useState<SortKey>("deadline");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // The row currently open in the edit modal, or null when not editing.
  const [editing, setEditing] = useState<Application | null>(null);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = applications.filter((app) => {
      if (typeFilter !== "all" && app.type !== typeFilter) return false;
      if (query) {
        const haystack =
          `${app.organization} ${app.role_or_program}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });

    const sorted = [...filtered].sort((a, b) => {
      if (sort === "priority") {
        const rank = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
        return rank !== 0 ? rank : byDeadline(a, b);
      }
      return byDeadline(a, b);
    });

    return sorted;
  }, [applications, typeFilter, sort, search]);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  

  return (
    <div className="flex flex-col gap-6">
      {/* Header: title + count on the left, search + primary action on the right */}
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-semibold tracking-tight text-ink">
              Applications
            </h1>
            <span className="rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-ink-soft">
              {visible.length} shown
            </span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search organization or role"
            className="w-64 rounded-interactive border border-line bg-surface px-3.5 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
          />
          {/* Primary action, the anchor of the purple accent. Opens the create
              modal by flipping this page's isCreateOpen state to true. */}
          <button
            type="button"
            onClick={() => setIsCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-interactive bg-accent px-4 py-2 text-sm font-medium text-ink shadow-glow transition-colors hover:bg-accent-hover active:bg-accent-press"
          >
            <span className="text-base leading-none">+</span>
            New application
          </button>
        </div>
      </header>

      <ApplicationsToolbar
        typeFilter={typeFilter}
        onTypeFilter={setTypeFilter}
        sort={sort}
        onSort={setSort}
      />

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
          onSelect={(id) => {
            setSelectedId(id);
            setEditing(applications.find((a) => a.id === id) ?? null);
          }}
        />
      )}

      {/* Create: no application prop, so the modal opens blank. */}
      {isCreateOpen && (
        <ApplicationFormModal
          onClose={() => setIsCreateOpen(false)}
          onSaved={() => {
            refetch();
            setIsCreateOpen(false);
          }}
        />
      )}

      {/* Edit: the clicked row is passed in, so the modal opens pre-filled and
          shows Delete. Same component, driven by whether `editing` is set. */}
      {editing && (
        <ApplicationFormModal
          application={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            refetch();
            setEditing(null);
          }}
        />
      )}
    </div>
  );
}

// A calm empty/loading/error frame that matches the table container.
function StatePanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-frame border border-line-strong bg-surface px-6 py-16 text-center text-sm text-ink-muted">
      {children}
    </div>
  );
}
