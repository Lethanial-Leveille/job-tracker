import { useState } from "react";
import type { ReactNode } from "react";
import { BackgroundTexture } from "./BackgroundTexture";
import { Sidebar } from "./Sidebar";
import type { View } from "./Sidebar";

interface Props {
  current: View;
  onNavigate: (view: View) => void;
  applicationCount: number;
  onLogout: () => void;
  children: ReactNode;
}

const COLLAPSE_KEY = "prowl_sidebar_collapsed";

// The frame that holds everything. On desktop it's a sidebar + a scrolling
// content column, and the sidebar can be collapsed (click the chevron) to give
// the content the full width; the choice is remembered. On phones the sidebar
// would eat most of the width, so it's always a slide-in overlay behind a menu
// button. "Drama in the frame": heavy styling on the chrome, calm content.
export function AppShell({ current, onNavigate, applicationCount, onLogout, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });

  const toggleCollapsed = () =>
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0");
      } catch {
        // Private mode / blocked storage: still collapse for this session.
      }
      return next;
    });

  // Navigating on mobile also closes the overlay, so a tap takes you straight to
  // the screen rather than leaving the menu covering it.
  const navigate = (view: View) => {
    onNavigate(view);
    setMenuOpen(false);
  };

  return (
    <div className="relative min-h-screen bg-base text-ink-soft">
      <BackgroundTexture />

      {/* Desktop-only reopen button, shown when the sidebar is collapsed. Fixed
          in the top-left margin so it doesn't shift the content. */}
      {collapsed && (
        <button
          type="button"
          onClick={toggleCollapsed}
          aria-label="Open sidebar"
          className="fixed left-3 top-3 z-30 hidden size-9 place-items-center rounded-interactive border border-line bg-surface text-ink-soft transition-colors hover:border-line-strong hover:text-ink md:grid"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M3 5h12M3 9h12M3 13h12" />
          </svg>
        </button>
      )}

      {/* Mobile top bar (md:hidden). Carries the wordmark and the menu toggle. */}
      <div className="relative z-20 flex items-center justify-between border-b border-line-strong bg-surface/80 px-4 py-3 backdrop-blur md:hidden">
        <span className="text-sm font-semibold tracking-[0.2em] text-ink">PROWL</span>
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          className="grid size-9 place-items-center rounded-interactive border border-line text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M3 5h12M3 9h12M3 13h12" />
          </svg>
        </button>
      </div>

      <div
        className={`relative z-10 md:grid ${
          collapsed ? "md:grid-cols-[1fr]" : "md:grid-cols-[248px_1fr]"
        }`}
      >
        {/* Desktop sidebar: a static grid column, hidden when collapsed. */}
        <div className={collapsed ? "hidden" : "hidden md:block"}>
          <Sidebar
            current={current}
            onNavigate={navigate}
            applicationCount={applicationCount}
            onLogout={onLogout}
            onCollapse={toggleCollapsed}
          />
        </div>

        {/* Mobile sidebar: a slide-in overlay, mounted only while open. No
            collapse control here — on mobile the whole thing is already hidden. */}
        {menuOpen && (
          <div className="fixed inset-0 z-40 md:hidden">
            <button
              type="button"
              aria-label="Close menu"
              onClick={() => setMenuOpen(false)}
              className="absolute inset-0 bg-black/60 backdrop-blur-[2px]"
            />
            <div className="absolute inset-y-0 left-0 w-[248px]">
              <Sidebar
                current={current}
                onNavigate={navigate}
                applicationCount={applicationCount}
                onLogout={onLogout}
              />
            </div>
          </div>
        )}

        {/* Content: its own scroll column on desktop; natural page scroll on
            mobile (the top bar takes the fixed height there). */}
        <main className="px-4 py-6 md:h-screen md:overflow-y-auto md:px-8 md:py-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}
