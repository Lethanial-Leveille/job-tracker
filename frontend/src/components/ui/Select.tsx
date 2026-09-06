// A themed dropdown, replacing the native <select>.
//
// WHY THIS EXISTS: a native select's open list is drawn by the operating system,
// outside the page. CSS cannot reach it, so it always arrived as generic OS
// chrome in the middle of a dark app. The closed state was ours; the open one
// never could be.
//
// The two reasons StatusSelect originally chose native are both answered here:
//
//   1. CLIPPING. ApplicationsTable is `overflow-hidden` (it rounds the first and
//      last row corners), so a menu positioned inside a row would be cut off.
//      This one renders through a PORTAL to document.body and positions itself
//      from the trigger's bounding rect, so no ancestor's overflow can touch it.
//   2. FREE ACCESSIBILITY. Rebuilt deliberately: listbox/option roles, arrow
//      keys, Enter/Space, Escape, Home/End, click-outside, and focus returning
//      to the trigger on close.
//
// Because the menu is position:fixed against a rect captured at open time, that
// rect goes stale the moment anything scrolls. Rather than track it, the menu
// closes on scroll or resize — simpler, and it matches what a native select does.

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";

export interface SelectOption<T extends string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  ariaLabel: string;
  /** Classes for the trigger button, so each site keeps its own look. */
  className?: string;
  /** Trigger content. Defaults to the selected option's label. */
  children?: ReactNode;
  /** Floor for the menu width; it never renders narrower than the trigger. */
  menuMinWidth?: number;
}

const MENU_MAX_HEIGHT = 280;

export function Select<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
  children,
  menuMinWidth = 180,
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  // The keyboard-highlighted row, which is NOT the same as the selected one:
  // you arrow through options before committing to any of them.
  const [active, setActive] = useState(0);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selectedIndex = Math.max(
    0,
    options.findIndex((o) => o.value === value),
  );

  function openMenu() {
    setRect(triggerRef.current?.getBoundingClientRect() ?? null);
    setActive(selectedIndex);
    setOpen(true);
  }

  function closeMenu(returnFocus = true) {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  }

  function choose(next: T) {
    onChange(next);
    closeMenu();
  }

  // Move focus into the menu once it exists, so arrow keys land somewhere.
  useLayoutEffect(() => {
    if (open) menuRef.current?.focus();
  }, [open]);

  // Dismissal: a pointer outside, any scroll, or a resize.
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: PointerEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      closeMenu(false);
    };
    // Capture phase so a scroll inside the content column counts, not just the
    // window's own.
    const onScrollOrResize = () => closeMenu(false);

    document.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open]);

  function onTriggerKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openMenu();
    }
  }

  function onMenuKeyDown(e: ReactKeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeMenu();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + options.length) % options.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const option = options[active];
      if (option) choose(option.value);
    } else if (e.key === "Tab") {
      closeMenu(false);
    }
  }

  // Flip above the trigger when there isn't room below, so the menu is never
  // half off-screen (a row near the bottom of a long list).
  const flipUp =
    rect !== null &&
    rect.bottom + MENU_MAX_HEIGHT > window.innerHeight &&
    rect.top > window.innerHeight - rect.bottom;

  const selectedLabel =
    options.find((o) => o.value === value)?.label ?? String(value);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onTriggerKeyDown}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={className}
      >
        {children ?? selectedLabel}
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={menuRef}
            role="listbox"
            tabIndex={-1}
            aria-label={ariaLabel}
            aria-activedescendant={`${listId}-${active}`}
            onKeyDown={onMenuKeyDown}
            style={{
              position: "fixed",
              left: Math.max(8, Math.min(rect.left, window.innerWidth - menuMinWidth - 8)),
              ...(flipUp
                ? { bottom: window.innerHeight - rect.top + 6 }
                : { top: rect.bottom + 6 }),
              minWidth: Math.max(rect.width, menuMinWidth),
              maxHeight: MENU_MAX_HEIGHT,
            }}
            className="z-[70] overflow-y-auto rounded-frame border border-line-strong bg-surface p-1 shadow-lg outline-none"
          >
            {options.map((option, i) => {
              const isSelected = option.value === value;
              return (
                <div
                  key={option.value}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => choose(option.value)}
                  onMouseEnter={() => setActive(i)}
                  className={`flex cursor-pointer items-center gap-2 rounded-interactive px-2.5 py-1.5 text-[13px] transition-colors ${
                    i === active ? "bg-surface-hover text-ink" : "text-ink-soft"
                  }`}
                >
                  {/* A fixed-width slot for the tick, so labels stay aligned
                      whether or not a row is the selected one. */}
                  <span className="w-3 shrink-0 text-accent">
                    {isSelected ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <path d="m5 13 4 4L19 7" />
                      </svg>
                    ) : null}
                  </span>
                  {option.label}
                </div>
              );
            })}
          </div>,
          document.body,
        )}
    </>
  );
}
