import { useMemo, useState } from "react";
import type { Application, Priority } from "../../lib/types";
import type { ApplicationsState } from "../../lib/useApplications";
import { deleteApplication } from "../../lib/api";
import { ApplicationsTable } from "./ApplicationsTable";
import {
  ApplicationsToolbar,
  type SortKey,
  type TypeFilter,
} from "./ApplicationsToolbar";
import { ApplicationFormModal } from "./ApplicationFormModal";
import { ApplicationDetail } from "./ApplicationDetail";
import { AddOpportunity } from "./AddOpportunity";
import { TailorPanel } from "./TailorPanel";
import { Drawer } from "../layout/Drawer";

const PRIORITY_RANK: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

// Deadline ascending with nulls last.
function byDeadline(a: Application, b: Application): number {
  if (a.deadline === b.deadline) return 0;
  if (a.deadline === null) return 1;
  if (b.deadline === null) return -1;
  return a.deadline < b.deadline ? -1 : 1;
}

// The command-center screen. It shows the pipeline table, and orchestrates the
// four overlays/views the redesign introduced: the full-screen Add flow, the
// detail drawer (row click), the tailor drawer (stacked over detail), and the
// edit modal (from the detail drawer).
export function ApplicationsPage({
  applications,
  loading,
  error,
  refetch,
}: ApplicationsState) {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [sort, setSort] = useState<SortKey>("deadline");
  const [search, setSearch] = useState("");

  const [adding, setAdding] = useState(false); // full-screen add view
  const [selectedId, setSelectedId] = useState<string | null>(null); // detail drawer
  const [editing, setEditing] = useState<Application | null>(null); // edit modal
  const [tailoring, setTailoring] = useState<Application | null>(null); // tailor drawer
  // Bumped when a tailored version is saved, so the open detail drawer refetches
  // its versions list.
  const [detailRefresh, setDetailRefresh] = useState(0);

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    const filtered = applications.filter((app) => {
      if (typeFilter !== "all" && app.type !== typeFilter) return false;
      if (query) {
        const haystack = `${app.organization} ${app.role_or_program}`.toLowerCase();
        if (!haystack.includes(query)) return false;
      }
      return true;
    });
    return [...filtered].sort((a, b) => {
      if (sort === "priority") {
        const rank = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
        return rank !== 0 ? rank : byDeadline(a, b);
      }
      return byDeadline(a, b);
    });
  }, [applications, typeFilter, sort, search]);

  // Resolve the selected/tailoring rows from the live list so they stay fresh
  // after a refetch.
  const selected = applications.find((a) => a.id === selectedId) ?? null;

  async function handleDelete(app: Application) {
    if (!window.confirm("Delete this application? This cannot be undone.")) return;
    await deleteApplication(app.id);
    setSelectedId(null);
    refetch();
  }

  // The Add flow is a full screen: it replaces the list entirely (sidebar stays).
  if (adding) {
    return (
      <AddOpportunity
        onClose={() => setAdding(false)}
        onSaved={() => {
          refetch();
          setAdding(false);
        }}
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
            Every internship and scholarship you're tracking, in one pipeline.
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
          onSelect={(id) => setSelectedId(id)}
        />
      )}

      {/* Detail drawer — opens on row click. */}
      <Drawer
        open={selected !== null}
        onClose={() => setSelectedId(null)}
        labelledBy="detail-title"
      >
        {selected && (
          <ApplicationDetail
            key={`${selected.id}-${detailRefresh}`}
            application={selected}
            onClose={() => setSelectedId(null)}
            onEdit={(app) => {
              setSelectedId(null);
              setEditing(app);
            }}
            onTailor={(app) => setTailoring(app)}
            onDelete={handleDelete}
          />
        )}
      </Drawer>

      {/* Tailor drawer — stacks over the detail drawer. */}
      <Drawer
        open={tailoring !== null}
        onClose={() => setTailoring(null)}
        elevated
      >
        {tailoring && (
          <TailorPanel
            application={tailoring}
            onClose={() => setTailoring(null)}
            onSaved={() => setDetailRefresh((n) => n + 1)}
          />
        )}
      </Drawer>

      {/* Edit modal — reached from the detail drawer's Edit button. */}
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

function StatePanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-frame border border-line-strong bg-surface px-6 py-16 text-center text-sm text-ink-muted">
      {children}
    </div>
  );
}
