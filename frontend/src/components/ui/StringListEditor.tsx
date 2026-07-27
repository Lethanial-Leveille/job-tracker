// Edits a list of strings — the resume's bullets, skill items, honors,
// coursework, tools, and links are all `string[]`, so this one component covers
// all six. Add appends a blank row, each row edits in place, and a ✕ removes it.
// Reuses Field's input styling so a bullet row looks like every other input.
//
// Immutable updates (map/filter to a new array) so React sees a new reference and
// re-renders — never mutate the incoming array in place.

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

  return (
    <div className="flex flex-col gap-2">
      <span className={labelTextClass}>{label}</span>

      {items.map((item, i) => (
        // Index key is acceptable here: rows are edited/appended/removed as a
        // simple ordered list, with no stable id to key on.
        <div key={i} className="flex items-start gap-2">
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
