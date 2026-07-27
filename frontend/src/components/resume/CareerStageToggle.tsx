// The student/professional segmented control, used in both shells. Neutral greys
// with a single accent touch (accent-subtle) on the active segment — the design
// system's scarce-purple rule: the toggle is chrome, so it earns at most one
// accent whisper, never the full glow (that's reserved for Save).

import type { CareerStage } from "./shell";

interface Props {
  value: CareerStage;
  onChange: (stage: CareerStage) => void;
}

const OPTIONS: { value: CareerStage; label: string }[] = [
  { value: "student", label: "Student" },
  { value: "professional", label: "Professional" },
];

export function CareerStageToggle({ value, onChange }: Props) {
  return (
    <div
      role="group"
      aria-label="Career stage"
      className="inline-flex rounded-interactive border border-line bg-base p-0.5"
    >
      {OPTIONS.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className={`rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors ${
              active
                ? "bg-accent-subtle text-ink"
                : "text-ink-muted hover:text-ink"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
