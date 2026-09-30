// A themed date picker popover, replacing the browser's native one.
//
// Same reason Select exists: the native picker is drawn by the browser, outside
// the page, so CSS cannot reach it and it arrives as generic chrome in the
// middle of a dark app.
//
// It borrows Select's two solutions wholesale. It renders through a PORTAL to
// document.body so the table's overflow-hidden cannot clip it, and it positions
// itself from the anchor's rect captured at open, closing on scroll or resize
// rather than chasing a rect that has gone stale.
//
// Unlike Select it does not own its trigger. The deadline cell's trigger is the
// whole cell, with its own content, so the parent renders the button, decides
// when this is open, and hands over the element to anchor to.
//
// Keyboard: arrows move a day or a week, PageUp/PageDown a month, Enter picks,
// Escape closes. Focus returns to the anchor on a keyboard close.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { addDays, fromIso, monthGrid, monthLabel, toIso, todayIso } from "../../lib/calendar";

interface Props {
  // The element the popover sits under (or over, near the bottom of the screen).
  anchor: HTMLElement;
  value: string | null; // ISO day, or null for no date
  onChange: (value: string | null) => void;
  onClose: () => void;
  ariaLabel: string;
  // Extra controls under the grid. The deadline cell puts its posting/mine
  // toggle here, which keeps this component about dates and nothing else.
  footer?: ReactNode;
}

const WIDTH = 264;
// Tall enough for the header, six weeks, and a footer, for the flip decision.
const HEIGHT = 340;
const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

export function DatePicker({ anchor, value, onChange, onClose, ariaLabel, footer }: Props) {
  // Captured once. The popover closes on scroll or resize, so it never goes stale.
  const [rect] = useState(() => anchor.getBoundingClientRect());
  const today = todayIso();
  // The keyboard-highlighted day, which is not the chosen one: you arrow around
  // before committing. The month on screen always follows it.
  const [active, setActive] = useState(value ?? today);
  const panelRef = useRef<HTMLDivElement>(null);

  const activeDate = fromIso(active);
  const year = activeDate.getFullYear();
  const month = activeDate.getMonth();
  const days = monthGrid(year, month);

  function close(returnFocus: boolean) {
    onClose();
    if (returnFocus) anchor.focus();
  }

  function pick(iso: string | null) {
    onChange(iso);
    close(true);
  }

  // Move a whole month, landing on the same day number where it exists
  // (January 31 -> February 28, not March 3).
  function shiftMonth(n: number) {
    const d = fromIso(active);
    const target = new Date(d.getFullYear(), d.getMonth() + n, 1);
    const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
    target.setDate(Math.min(d.getDate(), lastDay));
    setActive(toIso(target));
  }

  // Focus the panel once it exists, so arrow keys land somewhere.
  useLayoutEffect(() => {
    panelRef.current?.focus();
  }, []);

  // Dismissal: a pointer outside, any scroll, or a resize. A press on the
  // anchor is left to the anchor's own click, which toggles this closed.
  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (anchor.contains(target) || panelRef.current?.contains(target)) return;
      onClose();
    };
    const onScrollOrResize = () => onClose();
    document.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [anchor, onClose]);

  function onKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    const moves: Record<string, () => void> = {
      ArrowLeft: () => setActive(addDays(active, -1)),
      ArrowRight: () => setActive(addDays(active, 1)),
      ArrowUp: () => setActive(addDays(active, -7)),
      ArrowDown: () => setActive(addDays(active, 7)),
      PageUp: () => shiftMonth(-1),
      PageDown: () => shiftMonth(1),
      Enter: () => pick(active),
      Escape: () => close(true),
    };
    const move = moves[e.key];
    if (move) {
      e.preventDefault();
      move();
    } else if (e.key === "Tab" && !footer) {
      // Nothing else to tab to inside, so Tab leaves, and the popover with it.
      close(false);
    }
  }

  const flipUp =
    rect.bottom + HEIGHT > window.innerHeight && rect.top > window.innerHeight - rect.bottom;

  const navBtn =
    "grid size-7 place-items-center rounded-interactive text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink";

  return createPortal(
    // React events bubble through the component tree, NOT the page's layout, so
    // a click in here would still reach the table row that rendered it and open
    // the drawer, even though the popover sits on document.body. Stopping both
    // events at the root keeps the popover self contained.
    <div
      ref={panelRef}
      role="dialog"
      aria-label={ariaLabel}
      tabIndex={-1}
      onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        onKeyDown(e);
      }}
      style={{
        position: "fixed",
        width: WIDTH,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - WIDTH - 8)),
        ...(flipUp ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
      }}
      className="z-[70] flex flex-col gap-2 rounded-frame border border-line-strong bg-surface p-3 shadow-lg outline-none"
    >
      <div className="flex items-center justify-between">
        <button type="button" onClick={() => shiftMonth(-1)} aria-label="Previous month" className={navBtn}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m15 6-6 6 6 6" />
          </svg>
        </button>
        <span className="text-[13px] font-semibold text-ink" aria-live="polite">
          {monthLabel(year, month)}
        </span>
        <button type="button" onClick={() => shiftMonth(1)} aria-label="Next month" className={navBtn}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </button>
      </div>

      <div role="grid" aria-label={monthLabel(year, month)} className="grid grid-cols-7 gap-0.5">
        {WEEKDAYS.map((d, i) => (
          <span
            key={i}
            role="columnheader"
            className="pb-1 text-center text-[10.5px] font-semibold uppercase tracking-[0.08em] text-ink-muted"
          >
            {d}
          </span>
        ))}
        {days.map((iso) => {
          const inMonth = fromIso(iso).getMonth() === month;
          const selected = iso === value;
          const isActive = iso === active;
          const isToday = iso === today;
          // One accent, spent on the chosen day. Today gets a hairline ring,
          // the keyboard cursor a grey lift, so the three never look alike.
          const tone = selected
            ? "bg-accent text-ink font-semibold"
            : isActive
              ? "bg-surface-hover text-ink"
              : inMonth
                ? "text-ink-soft hover:bg-surface-hover hover:text-ink"
                : "text-ink-ghost hover:bg-surface-hover hover:text-ink-soft";
          return (
            <button
              key={iso}
              type="button"
              role="gridcell"
              tabIndex={-1}
              aria-selected={selected}
              aria-label={fromIso(iso).toLocaleDateString("en-US", {
                weekday: "long",
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
              onClick={() => pick(iso)}
              // Only within the month: the view follows `active`, so hovering a
              // spill-over day would flip the whole grid under the pointer.
              onMouseEnter={() => inMonth && setActive(iso)}
              className={`grid h-8 place-items-center rounded-interactive text-[12.5px] tabular-nums transition-colors ${tone} ${
                isToday && !selected ? "ring-1 ring-inset ring-accent-line" : ""
              }`}
            >
              {fromIso(iso).getDate()}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-line pt-2">
        {footer ?? <span />}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => pick(today)}
            className="rounded-interactive px-2 py-1 text-[12px] text-ink-soft transition-colors hover:bg-surface-hover hover:text-ink"
          >
            Today
          </button>
          {value !== null && (
            <button
              type="button"
              onClick={() => pick(null)}
              className="rounded-interactive px-2 py-1 text-[12px] text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
