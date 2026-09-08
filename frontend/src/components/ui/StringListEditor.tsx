// Edits a list of strings — the resume's bullets, skill items, honors,
// coursework, tools, and links are all `string[]`, so this one component covers
// all six. Add appends a blank row, each row edits in place, and a ✕ removes it.
// Reuses Field's input styling so a bullet row looks like every other input.
//
// Immutable updates (map/filter to a new array) so React sees a new reference and
// re-renders — never mutate the incoming array in place.
//
// ORDER IS MEANINGFUL, which is why rows drag. Every consumer of these lists
// treats position as relevance: the tailoring prompt keeps the strongest first,
// `fit_to_one_page` cuts from the END, and the general resume takes the first N
// bullets of each entry. So "move this bullet up" is the control that decides
// what actually prints, and until now there was no way to do it.
//
// Drag lives on a HANDLE rather than the whole row: making a row draggable
// breaks click-to-position and text selection inside its own textarea. The
// handle is also a button that responds to arrow keys, so reordering works
// without a mouse — dragging alone would be unusable by keyboard.

import { useState } from "react";
import { fieldClass, labelTextClass } from "./Field";

interface Props {
  label: string;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
  addLabel?: string;
  multiline?: boolean;
}

export function StringListEditor({
  label,
  items,
  onChange,
  placeholder,
  addLabel = "Add",
  multiline = false,
}: Props) {
  const update = (index: number, value: string) =>
    onChange(items.map((item, i) => (i === index ? value : item)));
  const remove = (index: number) =>
    onChange(items.filter((_, i) => i !== index));
  const add = () => onChange([...items, ""]);

  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);

  function move(from: number, to: number) {
    if (to < 0 || to >= items.length || from === to) return;
    const next = [...items];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-2">
      <span className={labelTextClass}>{label}</span>

      {items.map((item, i) => (
        // Index key is acceptable here: rows are edited/appended/removed as a
        // simple ordered list, with no stable id to key on.
        <div
          key={i}
          onDragOver={(e) => {
            // Required: without preventDefault the drop never fires.
            if (dragIndex === null) return;
            e.preventDefault();
            setOverIndex(i);
          }}
          onDrop={(e) => {
            if (dragIndex === null) return;
            e.preventDefault();
            move(dragIndex, i);
            setDragIndex(null);
            setOverIndex(null);
          }}
          className={`flex items-start gap-2 rounded-interactive transition-colors ${
            overIndex === i && dragIndex !== null && dragIndex !== i
              ? "bg-surface-raised"
              : ""
          } ${dragIndex === i ? "opacity-50" : ""}`}
        >
          <button
            type="button"
            draggable
            onDragStart={() => setDragIndex(i)}
            onDragEnd={() => {
              setDragIndex(null);
              setOverIndex(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowUp") {
                e.preventDefault();
                move(i, i - 1);
              } else if (e.key === "ArrowDown") {
                e.preventDefault();
                move(i, i + 1);
              }
            }}
            aria-label={`Reorder ${label} item ${i + 1}. Use arrow keys to move.`}
            title="Drag to reorder, or focus and use arrow keys"
            className="mt-0.5 grid size-9 shrink-0 cursor-grab place-items-center rounded-interactive text-ink-muted transition-colors hover:text-ink active:cursor-grabbing"
          >
            <svg className="size-4" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="9" cy="6" r="1.5" />
              <circle cx="15" cy="6" r="1.5" />
              <circle cx="9" cy="12" r="1.5" />
              <circle cx="15" cy="12" r="1.5" />
              <circle cx="9" cy="18" r="1.5" />
              <circle cx="15" cy="18" r="1.5" />
            </svg>
          </button>
          {multiline ? (
            <textarea
              className={`${fieldClass} min-h-[64px] flex-1 resize-y`}
              value={item}
              placeholder={placeholder}
              onChange={(e) => update(i, e.target.value)}
            />
          ) : (
            <input
              className={`${fieldClass} flex-1`}
              value={item}
              placeholder={placeholder}
              onChange={(e) => update(i, e.target.value)}
            />
          )}
          <button
            type="button"
            onClick={() => remove(i)}
            aria-label={`Remove ${label} item`}
            className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-interactive border border-line text-ink-muted transition-colors hover:border-line-strong hover:text-ink"
          >
            <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={add}
        className="self-start rounded-interactive border border-line bg-base px-3 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink"
      >
        + {addLabel}
      </button>
    </div>
  );
}
