import { useState } from "react";
import type { Application, ApplicationStatus } from "../../lib/types";
import { monogram } from "../../lib/format";
import { StatusSelect } from "./StatusSelect";
import { DetailOverview } from "./DetailOverview";
import { StatusTimeline } from "./StatusTimeline";
import { TailorTab } from "./TailorTab";

// One application, as a full screen that replaces the list. This is what the
// detail drawer, the tailor drawer stacked on top of it, and the edit modal
// launched from underneath both collapsed into.
//
// The old arrangement was three overlays deep, all of the same shape, so
// backing out of tailoring landed you on the detail panel rather than the list
// and there was no reliable sense of where you were. There is exactly one layer
// now: the list, or one application. Back always means the list.
//
// The pattern (same one AddOpportunity already uses): a view swap driven by
// parent state, not a router. Adding react-router for two screens would be more
// machinery than the app has earned.

type Tab = "overview" | "tailor";

interface Props {
  application: Application;
  onBack: () => void;
  onSaved: () => void; // an edit was saved -> parent refetches
  onDelete: (application: Application) => void;
  onStatusChange: (id: string, status: ApplicationStatus) => void;
}

export function ApplicationDetailPage({
  application,
  onBack,
  onSaved,
  onDelete,
  onStatusChange,
}: Props) {
  const [tab, setTab] = useState<Tab>("overview");
  // Whether the Tailor tab has ever been opened. Both tabs stay MOUNTED once
  // shown and are hidden with CSS rather than unmounted — see the note at the
  // render below, which is the difference between a tab switch being free and
  // it costing you a paid Opus call and any half-typed edits.
  const [tailorOpened, setTailorOpened] = useState(false);

  function openTab(next: Tab) {
    if (next === "tailor") setTailorOpened(true);
    setTab(next);
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Back bar. Mirrors the add flow's, so leaving any full screen view
          looks and sits in the same place. */}
      <div className="border-b border-line pb-5">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex w-fit items-center gap-2 rounded-interactive border border-line bg-surface px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="m15 18-6-6 6-6" />
          </svg>
          Applications
        </button>
      </div>

      {/* Identity header */}
      <header className="flex flex-wrap items-start justify-between gap-5">
        <div className="flex min-w-0 items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-frame border border-line-strong bg-surface-hover text-base font-semibold text-ink-soft">
            {monogram(application.organization)}
          </span>
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold tracking-tight text-ink">
              {application.organization}
            </h1>
            <p className="mt-1 truncate text-sm text-ink-soft">
              {application.role_or_program}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Same control as the table, so status works identically wherever
              you happen to be looking at the row. */}
          <StatusSelect application={application} onChange={onStatusChange} />
          {application.posting_url && (
            <a
              href={application.posting_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-interactive border border-line bg-surface px-3 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 4h6v6M20 4l-8 8" />
                <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" />
              </svg>
              Posting
            </a>
          )}
        </div>
      </header>

      {/* Tabs. Two, deliberately: everything about the application, and
          everything about its resume. A third would mean the page is doing too
          much again. */}
      <div
        role="tablist"
        className="inline-flex w-fit items-center gap-1 rounded-interactive border border-line bg-surface p-1"
      >
        <TabButton active={tab === "overview"} onClick={() => openTab("overview")}>
          Overview
        </TabButton>
        <TabButton active={tab === "tailor"} onClick={() => openTab("tailor")}>
          Tailor resume
        </TabButton>
      </div>

      {/* Hidden, not unmounted. Swapping the two with a ternary looks tidier
          and is wrong twice over:
            - TailorTab generates a draft on mount. Unmounting on every tab
              switch would re-run a PAID Opus call each time you glanced at
              Overview and came back, and throw away the draft you were reading.
            - DetailOverview holds your in-progress edits in state. Unmounting
              would silently discard anything typed but not yet saved.
          The Tailor tab is still mounted LAZILY — not until first opened — so
          simply viewing an application never spends a call. */}
      <div className={tab === "overview" ? undefined : "hidden"}>
        <div className="flex flex-col gap-8">
          <DetailOverview
            application={application}
            onSaved={onSaved}
            onDelete={onDelete}
          />
          <StatusTimeline application={application} />
        </div>
      </div>
      {tailorOpened && (
        <div className={tab === "tailor" ? undefined : "hidden"}>
          <TailorTab application={application} onStatusChange={onStatusChange} />
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      // Grey lift for the active tab, not purple: navigation is not on the
      // accent's short list in docs/design.md.
      className={`rounded-md px-3.5 py-1.5 text-[13px] font-medium transition-colors ${
        active ? "bg-surface-hover text-ink" : "text-ink-muted hover:text-ink-soft"
      }`}
    >
      {children}
    </button>
  );
}
