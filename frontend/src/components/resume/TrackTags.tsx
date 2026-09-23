import type { ResumeTrack } from "./shell";

// Which resume flavours an entry belongs to, as two toggles.
//
// Nothing selected means "both", and that is the default rather than a state
// you have to choose. Most projects are worth showing whoever is reading, and
// making every new entry a two-step job is how the tags end up wrong.
//
// What a tag means differs by section and the difference is deliberate. On a
// PROJECT it both promotes and excludes: tagging it says this is the one to
// open with for that reader, and by the same token that it does not belong to
// the other. On a SKILLS row it only promotes, because dropping a project the
// reader does not care about buys space on a one-page resume, where dropping a
// skills row just hides something you can do.

const OPTIONS: { value: ResumeTrack; label: string }[] = [
  { value: "swe", label: "Software" },
  { value: "embedded", label: "Embedded" },
];

export function TrackTags({
  value,
  onChange,
  hint,
}: {
  value: ResumeTrack[] | undefined;
  onChange: (tracks: ResumeTrack[]) => void;
  hint: string;
}) {
  const selected = value ?? [];

  function toggle(track: ResumeTrack) {
    onChange(
      selected.includes(track)
        ? selected.filter((t) => t !== track)
        : [...selected, track],
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-muted">
        Flavour
      </span>
      {OPTIONS.map((o) => {
        const active = selected.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => toggle(o.value)}
            aria-pressed={active}
            className={`rounded-interactive border px-2.5 py-1 text-[11.5px] transition-colors ${
              active
                ? "border-accent-line bg-accent-subtle text-ink"
                : "border-line text-ink-muted hover:border-line-strong hover:text-ink-soft"
            }`}
          >
            {o.label}
          </button>
        );
      })}
      <span className="text-[11px] text-ink-muted">
        {selected.length === 0 ? "On both" : hint}
      </span>
    </div>
  );
}
