import { Link, useSearchParams } from "react-router-dom";
import { SAVED_VIEWS } from "../applications/views";
import type { ReactNode } from "react";

// --- Icons (thin line set, drawn to a shared 18px box) ----------------------

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const icons = {
  applications: (
    <Icon>
      <rect x="2.5" y="3" width="13" height="4" rx="1" />
      <rect x="2.5" y="11" width="13" height="4" rx="1" />
    </Icon>
  ),
  // A radar sweep: the feed looking for postings rather than you doing it.
  discovered: (
    <Icon>
      <circle cx="9" cy="9" r="6.5" />
      <circle cx="9" cy="9" r="2.5" />
      <path d="M9 9 13.6 4.4" />
    </Icon>
  ),
  documents: (
    <Icon>
      <path d="M4 2.5h6l4 4v9a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5Z" />
      <path d="M10 2.5V6.5h4" />
    </Icon>
  ),
};

// --- Nav model --------------------------------------------------------------

export type View = "applications" | "discovered" | "resume";

// Only real destinations live here. Deadlines, Organizations and Analytics used
// to sit in this list as disabled "Soon" placeholders, which meant three of five
// nav items went nowhere — the clearest signal in the whole app that it was a
// scaffold rather than a tool. A nav should advertise what exists; add an entry
// when its screen does.
interface NavItem {
  key: keyof typeof icons;
  label: string;
  view: View;
}

const WORKSPACE: NavItem[] = [
  { key: "applications", label: "Applications", view: "applications" },
  { key: "discovered", label: "Discovered", view: "discovered" },
  { key: "documents", label: "Resume", view: "resume" },
];

interface Props {
  current: View;
  onNavigate: (view: View) => void;
  applicationCount: number;
  onLogout: () => void;
  // Desktop only: collapse to an icon rail. Omitted in the mobile overlay, which
  // already dismissed by tapping outside it.
  onCollapse?: () => void;
  // Narrow rail: icons only, no labels, no saved views. NOT hidden — losing the
  // nav entirely to gain 248 pixels is a bad trade, and the reopen control then
  // has to live somewhere arbitrary. The rail keeps every destination one click
  // away and keeps the page's left edge where it was.
  collapsed?: boolean;
}

export function Sidebar({
  current,
  onNavigate,
  applicationCount,
  onLogout,
  onCollapse,
  collapsed = false,
}: Props) {
  // Read here rather than threaded down: a saved view lives in the URL, so the
  // nav can highlight the active one without the route above it holding state.
  const [searchParams] = useSearchParams();
  const activeView = searchParams.get("view");

  return (
    <aside
      // The geometric wash lives in the CHROME, never behind data. Two radial
      // gradients at 3.5-7% — texture you feel rather than see, per design.md.
      style={{
        backgroundImage:
          "radial-gradient(120% 70% at 8% 0%, rgb(139 92 246 / 0.07), transparent 58%), radial-gradient(90% 50% at 95% 100%, rgb(139 92 246 / 0.035), transparent 70%)",
      }}
      className={`relative z-10 flex h-screen flex-col gap-8 border-r border-line-strong bg-surface/60 py-6 backdrop-blur-sm ${
        collapsed ? "px-2" : "px-4"
      }`}
    >
      {/* Wordmark. The logo is the collapse control now — the chevron that used
          to sit here was a second small target doing a job the brand mark can do
          while taking up no extra room, and it read as decoration until you
          found out otherwise. */}
      <div className={`flex items-center gap-3 ${collapsed ? "justify-center px-0" : "px-2"}`}>
        <button
          type="button"
          onClick={onCollapse}
          disabled={!onCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand" : "Collapse"}
          className="shrink-0 rounded-interactive transition-opacity hover:opacity-80 disabled:cursor-default disabled:hover:opacity-100"
        >
          <LogoMark />
        </button>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-[0.2em] text-ink">
              PROWL
            </div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">
              Opportunity Tracker
            </div>
          </div>
        )}
      </div>

      {/* Workspace nav */}
      <nav className="flex flex-col gap-1">
        {WORKSPACE.map((item) => {
          // Capture the narrowed view in a const: TS widens item.view back to
          // View | undefined inside the onClick closure, but a local const holds
          // the narrowing.
          const view = item.view;
          const active = view === current;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => onNavigate(view)}
              aria-current={active ? "page" : undefined}
              // The label is what the tooltip carries once it is gone from the
              // button, so a rail is still readable to someone who has not
              // memorised five icons.
              title={collapsed ? item.label : undefined}
              className={`${
                collapsed
                  ? "flex items-center justify-center rounded-interactive border-l-2 py-2"
                  : "flex items-center gap-3 rounded-interactive border-l-2 px-3 py-2 text-sm"
              } ${
                active
                  ? "border-l-accent bg-accent-subtle font-medium text-ink"
                  : "border-l-transparent text-ink-soft transition-colors hover:text-ink"
              }`}
            >
              <span className={active ? "text-accent" : undefined}>{icons[item.key]}</span>
              {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
              {!collapsed && item.view === "applications" && (
                <span className="text-xs text-ink-soft">{applicationCount}</span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Saved views. A third block, deliberately below the two real
          destinations: these are not places, they are questions asked of the
          Applications list. Each is a client-side predicate over data already
          fetched (components/applications/views.ts), so the nav still advertises
          only what exists — clicking one takes you somewhere real.

          Only rendered on the Applications screen: a view of a list you are not
          looking at is a link to a different page wearing a filter's clothes. */}
      {current === "applications" && !collapsed && (
        <div className="flex flex-col gap-1">
          <div className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
            Views
          </div>
          {SAVED_VIEWS.map((view) => {
            const active = activeView === view.key;
            return (
              <Link
                key={view.key}
                // Clicking the active one clears it, so the block toggles rather
                // than trapping you in a filter with no visible way out.
                to={active ? "/applications" : `/applications?view=${view.key}`}
                aria-current={active ? "true" : undefined}
                className={`rounded-interactive px-3 py-1.5 text-[13px] transition-colors ${
                  active
                    ? "bg-surface-hover text-ink"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                {view.label}
              </Link>
            );
          })}
        </div>
      )}

      {/* User card, pinned to the bottom. mt-auto pushes it down past the nav.
          On the rail it drops to the avatar and the sign-out, stacked: a name
          and a cycle label are context, and context is the first thing a narrow
          column should give up. */}
      <div
        className={`mt-auto flex rounded-frame border border-line bg-surface-hover ${
          collapsed ? "flex-col items-center gap-2 p-2" : "items-center gap-3 p-3"
        }`}
      >
        <span
          title={collapsed ? "Lee Leveille" : undefined}
          className="grid size-8 shrink-0 place-items-center rounded-lg border border-line-strong bg-base text-xs font-semibold text-ink-soft"
        >
          LL
        </span>
        {!collapsed && (
          <div className="leading-tight">
            <div className="text-[13px] font-medium text-ink">Lee Leveille</div>
            <div className="text-[11px] text-ink-muted">Fall 2026 cycle</div>
          </div>
        )}
        <button
          type="button"
          onClick={onLogout}
          aria-label="Sign out"
          title="Sign out"
          className={`grid size-7 shrink-0 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink ${
            collapsed ? "" : "ml-auto"
          }`}
        >
          <Icon>
            <path d="M7 3.5H4a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3" />
            <path d="M10.5 11.5 14 8l-3.5-3.5M14 8H6.5" />
          </Icon>
        </button>
      </div>
    </aside>
  );
}

// A small abstract mark: a rounded purple tile with a nested geometric glyph.
// One of the few sanctioned purple elements (the brand mark), kept subtle.
function LogoMark() {
  return (
    <span className="grid size-9 place-items-center rounded-interactive bg-accent">
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <path
          d="M9 2 15 5.5V12.5L9 16 3 12.5V5.5Z"
          fill="none"
          stroke="#fff"
          strokeWidth="1.3"
          strokeLinejoin="round"
        />
        <path
          d="M9 5.5 12 7.25v3.5L9 12.5 6 10.75v-3.5Z"
          fill="#fff"
          fillOpacity="0.9"
        />
      </svg>
    </span>
  );
}
