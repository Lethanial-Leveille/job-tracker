// A labeled text input (or textarea). The first shared form primitive — every
// existing form re-declares these class strings per file; centralizing them here
// keeps the resume builder's many fields consistent. Exported class constants so
// StringListEditor reuses the exact same input look.
//
// onChange hands back the string value directly (not the event), so callers use
// the typed-setter style: onChange={(v) => set("field", v)}.

export const labelTextClass =
  "text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-muted";
export const labelClass = `flex flex-col gap-1.5 ${labelTextClass}`;
export const fieldClass =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  type?: string;
  multiline?: boolean;
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = "text",
  multiline = false,
}: Props) {
  return (
    <label className={labelClass}>
      {label}
      {multiline ? (
        <textarea
          className={`${fieldClass} min-h-[76px] resize-y`}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <input
          className={fieldClass}
          type={type}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </label>
  );
}
