// The resume-flavour segmented control, used in both shells. Neutral greys with
// a single accent touch (accent-subtle) on the active segment — the design
// system's scarce-purple rule: the toggle is chrome, so it earns at most one
// accent whisper, never the full glow (that's reserved for Save).
//
// This used to pick student versus professional, which chose the section
// ARRANGEMENT for two different people. There is only one person now, and the
// choice that matters every day is which flavour of the same student resume
// goes out: the general software one, or the embedded one.
//
// The arrangement setting still exists on the resume and still works; it simply
// has nothing left to decide, so it is no longer worth a control.

import type { ResumeTrack } from "./shell";

interface Props {
  value: ResumeTrack;
  onChange: (track: ResumeTrack) => void;
}

const OPTIONS: { value: ResumeTrack; label: string; hint: string }[] = [
  { value: "swe", label: "Software", hint: "Leads with Prowl" },
  { value: "embedded", label: "Embedded", hint: "Leads with FormFactor, hardware skills second" },
];

export function ResumeTrackToggle({ value, onChange }: Props) {
  return (
    <div
      role="group"
      aria-label="Resume flavour"
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
            // The hint lives in the tooltip rather than on the button: the
            // control has to stay small, and which projects a flavour leads with
            // is the thing you check once and then stop wondering about.
            title={o.hint}
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
