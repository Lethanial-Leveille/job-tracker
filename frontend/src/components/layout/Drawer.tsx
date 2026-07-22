import { useEffect } from "react";
import type { ReactNode } from "react";

// A right-hand slide-over panel over a dimmed backdrop — the redesign's way of
// showing detail and the tailoring flow without leaving the pipeline. Kept
// mounted by its parent (open toggles the slide) so it animates in and out; the
// parent passes children only when there's something to show.
//
// `elevated` bumps the z-index and narrows it slightly, so a second drawer (the
// tailor panel) can stack over the first (the detail panel).

interface Props {
  open: boolean;
  onClose: () => void;
  labelledBy?: string;
  elevated?: boolean;
  children: ReactNode;
}

export function Drawer({ open, onClose, labelledBy, elevated, children }: Props) {
  // Esc closes the topmost drawer. Bound only while open so a background drawer
  // doesn't also react.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      {/* Backdrop. The elevated drawer skips its own backdrop so the one beneath
          it stays visible through the dim. */}
      {!elevated && (
        <div
          onClick={onClose}
          aria-hidden="true"
          className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px] transition-opacity duration-200 motion-reduce:transition-none ${
            open ? "opacity-100" : "pointer-events-none opacity-0"
          }`}
        />
      )}

      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-hidden={!open}
        className={`fixed inset-y-0 right-0 flex w-[min(460px,94vw)] flex-col overflow-hidden border-l border-line-strong bg-surface shadow-[-30px_0_60px_-30px_rgba(0,0,0,0.7)] transition-transform duration-300 ease-out motion-reduce:transition-none ${
          elevated ? "z-[60] w-[min(500px,96vw)]" : "z-50"
        } ${open ? "translate-x-0" : "pointer-events-none translate-x-full"}`}
      >
        {children}
      </aside>
    </>
  );
}

// Shared drawer chrome, so the detail and tailor panels share one header shape.
export function DrawerHeader({
  children,
  onClose,
}: {
  children: ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="flex items-start gap-4 border-b border-line px-6 py-5">
      <div className="min-w-0 flex-1">{children}</div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="grid size-8 shrink-0 place-items-center rounded-lg text-lg leading-none text-ink-muted transition-colors hover:bg-surface-hover hover:text-ink"
      >
        ✕
      </button>
    </div>
  );
}
