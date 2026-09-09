// Keyboard navigation for the applications list.
//
// The list is the screen this app is opened on every day, and every action on it
// currently costs a trip to the mouse. j/k to move, ⏎ to open, e to mark applied
// turns a morning triage pass into something you can do without leaving the
// keyboard.
//
// Two rules it follows:
//
//   1. Never swallow a keystroke meant for a field. If focus is in an input,
//      textarea, select or anything contenteditable, this hook does nothing —
//      otherwise typing "e" in the search box would mark a row applied.
//   2. Every destructive-ish action is undoable rather than confirmed. Marking
//      applied fires immediately and offers ⌘Z, because a confirm dialog on an
//      action you take forty times a morning is worse than the mistake it
//      prevents. Same instinct as the optimistic status cell that rolls back.

import { useCallback, useEffect, useState } from "react";
import type { Application, ApplicationStatus } from "../../lib/types";

export interface UndoableChange {
  id: string;
  organization: string;
  from: ApplicationStatus;
  to: ApplicationStatus;
}

interface Options {
  applications: Application[];
  onOpen: (id: string) => void;
  onStatusChange: (id: string, status: ApplicationStatus) => void;
}

export interface ListKeyboard {
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  lastChange: UndoableChange | null;
  undo: () => void;
  dismissUndo: () => void;
}

function typingInAField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  return ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

export function useListKeyboard({
  applications,
  onOpen,
  onStatusChange,
}: Options): ListKeyboard {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [lastChange, setLastChange] = useState<UndoableChange | null>(null);

  const undo = useCallback(() => {
    if (!lastChange) return;
    onStatusChange(lastChange.id, lastChange.from);
    setLastChange(null);
  }, [lastChange, onStatusChange]);

  const dismissUndo = useCallback(() => setLastChange(null), []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // ⌘Z / Ctrl+Z works even from a field: undo is global, and a text field
      // has its own undo stack that this would otherwise shadow only when the
      // field is empty of history. Checked FIRST so the field guard below
      // cannot swallow it.
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
        if (!lastChange) return;
        event.preventDefault();
        undo();
        return;
      }
      if (typingInAField(event.target)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (applications.length === 0) return;

      const index = applications.findIndex((a) => a.id === selectedId);

      switch (event.key) {
        case "j":
        case "ArrowDown": {
          event.preventDefault();
          // From nothing, j selects the first row rather than the second.
          const next = index < 0 ? 0 : Math.min(index + 1, applications.length - 1);
          setSelectedId(applications[next].id);
          break;
        }
        case "k":
        case "ArrowUp": {
          event.preventDefault();
          const next = index < 0 ? 0 : Math.max(index - 1, 0);
          setSelectedId(applications[next].id);
          break;
        }
        case "Enter": {
          if (index < 0) return;
          event.preventDefault();
          onOpen(applications[index].id);
          break;
        }
        case "e": {
          if (index < 0) return;
          const app = applications[index];
          if (app.status === "applied") return;
          event.preventDefault();
          onStatusChange(app.id, "applied");
          setLastChange({
            id: app.id,
            organization: app.organization,
            from: app.status,
            to: "applied",
          });
          break;
        }
        case "Escape": {
          setSelectedId(null);
          break;
        }
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [applications, selectedId, onOpen, onStatusChange, undo, lastChange]);

  // A selection pointing at a row that filtering just removed would leave j/k
  // starting over from the top with no visible cursor. Drop it instead.
  useEffect(() => {
    if (selectedId && !applications.some((a) => a.id === selectedId)) {
      setSelectedId(null);
    }
  }, [applications, selectedId]);

  return { selectedId, setSelectedId, lastChange, undo, dismissUndo };
}
