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
  deadlines: (
    <Icon>
      <circle cx="9" cy="9" r="6.5" />
      <path d="M9 5.5V9l2.5 1.5" />
    </Icon>
  ),
  organizations: (
    <Icon>
      <path d="M3 15.5V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v11.5M11 7h3a1 1 0 0 1 1 1v7.5M2 15.5h14" />
      <path d="M5.5 6h3M5.5 9h3" />
    </Icon>
  ),
  documents: (
    <Icon>
      <path d="M4 2.5h6l4 4v9a.5.5 0 0 1-.5.5h-9a.5.5 0 0 1-.5-.5V3a.5.5 0 0 1 .5-.5Z" />
      <path d="M10 2.5V6.5h4" />
    </Icon>
  ),
  analytics: (
    <Icon>
      <path d="M2.5 15.5h13" />
      <path d="M5 12.5V9M9 12.5V5M13 12.5v-4.5" />
    </Icon>
  ),
};

// --- Nav model --------------------------------------------------------------
// Only Applications is real in v1. The rest are future features: rendered so
// the shell feels complete, but muted, non-clickable, and marked "Soon" — never
// showing a fabricated count.

interface NavItem {
  key: keyof typeof icons;
  label: string;
  active?: boolean;
}

const WORKSPACE: NavItem[] = [
  { key: "applications", label: "Applications", active: true },
  { key: "deadlines", label: "Deadlines" },
  { key: "organizations", label: "Organizations" },
  { key: "documents", label: "Documents" },
  { key: "analytics", label: "Analytics" },
];

interface Props {
  applicationCount: number;
  onLogout: () => void;
}

export function Sidebar({ applicationCount, onLogout }: Props) {
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
      </div>

      {/* Workspace nav */}
      <nav className="flex flex-col gap-1">
        <div className="px-3 pb-2 text-[10px] font-medium uppercase tracking-[0.18em] text-ink-muted">
          Workspace
        </div>
        {WORKSPACE.map((item) =>
          item.active ? (
            <a
              key={item.key}
              href="#"
              aria-current="page"
              className="flex items-center gap-3 rounded-interactive border-l-2 border-l-accent bg-accent-subtle px-3 py-2 text-sm font-medium text-ink shadow-glow"
            >
              <span className="text-accent">{icons[item.key]}</span>
              <span className="flex-1">{item.label}</span>
              <span className="text-xs text-ink-soft">{applicationCount}</span>
            </a>
          ) : (
            <span
              key={item.key}
              aria-disabled="true"
              className="flex cursor-default items-center gap-3 rounded-interactive border-l-2 border-l-transparent px-3 py-2 text-sm text-ink-muted"
            >
              <span>{icons[item.key]}</span>
              <span className="flex-1">{item.label}</span>
              <span className="rounded-full border border-line px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-ink-muted">
                Soon
              </span>
            </span>
          ),
        )}
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
    <span className="grid size-9 place-items-center rounded-interactive bg-accent shadow-glow">
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
