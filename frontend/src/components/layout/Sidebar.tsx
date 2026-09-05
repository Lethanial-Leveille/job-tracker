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
  documents: (
    <Icon>
      <path d="M4 2.5h6l4 4v9a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5Z" />
      <path d="M10 2.5V6.5h4" />
    </Icon>
  ),
};

// --- Nav model --------------------------------------------------------------

export type View = "applications" | "resume";

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
  { key: "documents", label: "Resume", view: "resume" },
];

interface Props {
  current: View;
  onNavigate: (view: View) => void;
  applicationCount: number;
  onLogout: () => void;
  // Desktop only: collapse the sidebar. Omitted in the mobile overlay, which is
  // already dismissed by tapping outside it.
  onCollapse?: () => void;
}

export function Sidebar({
  current,
  onNavigate,
  applicationCount,
  onLogout,
  onCollapse,
}: Props) {
  return (
    <aside className="relative z-10 flex h-screen flex-col gap-8 border-r border-line-strong bg-surface/60 px-4 py-6 backdrop-blur-sm">
      {/* Wordmark */}
      <div className="flex items-center gap-3 px-2">
        <LogoMark />
        <div className="leading-tight">
          <div className="text-sm font-semibold tracking-[0.2em] text-ink">
            PROWL
          </div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">
            Opportunity Tracker
          </div>
        </div>
        {onCollapse && (
          <button
            type="button"
            onClick={onCollapse}
            aria-label="Collapse sidebar"
            className="ml-auto grid size-7 shrink-0 place-items-center rounded-interactive text-ink-muted transition-colors hover:text-ink"
          >
            <svg width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 4 6 9l5 5" />
            </svg>
          </button>
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
              className={
                active
                  ? "flex items-center gap-3 rounded-interactive border-l-2 border-l-accent bg-accent-subtle px-3 py-2 text-sm font-medium text-ink"
                  : "flex items-center gap-3 rounded-interactive border-l-2 border-l-transparent px-3 py-2 text-sm text-ink-soft transition-colors hover:text-ink"
              }
            >
              <span className={active ? "text-accent" : undefined}>{icons[item.key]}</span>
              <span className="flex-1 text-left">{item.label}</span>
              {item.view === "applications" && (
                <span className="text-xs text-ink-soft">{applicationCount}</span>
              )}
            </button>
          );
        })}
      </nav>

      {/* User card, pinned to the bottom. mt-auto pushes it down past the nav. */}
      <div className="mt-auto flex items-center gap-3 rounded-frame border border-line bg-surface-hover p-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg border border-line-strong bg-base text-xs font-semibold text-ink-soft">
          LL
        </span>
        <div className="leading-tight">
          <div className="text-[13px] font-medium text-ink">Lee Leveille</div>
          <div className="text-[11px] text-ink-muted">Fall 2026 cycle</div>
        </div>
        <button
          type="button"
          onClick={onLogout}
          aria-label="Sign out"
          title="Sign out"
          className="ml-auto grid size-7 shrink-0 place-items-center rounded-lg border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
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
