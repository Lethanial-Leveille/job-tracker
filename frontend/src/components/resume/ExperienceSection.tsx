// Experience section: a repeatable list of jobs, each with a bullet bank.
// Controlled slice, same immutable-update pattern. Bullets use the multiline
// StringListEditor since accomplishment lines run long.

import type { Experience } from "../../lib/types";
import { Field } from "../ui/Field";
import { StringListEditor } from "../ui/StringListEditor";
import { EmptyHint, EntryBlock, SectionCard } from "../ui/SectionCard";

function blankExperience(): Experience {
  return { organization: "", role: "", location: "", dates: "", bullets: [] };
}

interface Props {
  items: Experience[];
  onChange: (items: Experience[]) => void;
}

export function ExperienceSection({ items, onChange }: Props) {
  const patch = (i: number, changes: Partial<Experience>) =>
    onChange(items.map((x, idx) => (idx === i ? { ...x, ...changes } : x)));
  const add = () => onChange([...items, blankExperience()]);
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <SectionCard
      title="Experience"
      description="Jobs and roles. Keep every bullet here; tailoring picks the strongest per application."
      onAdd={add}
      addLabel="Add position"
    >
      {items.length === 0 && <EmptyHint>No positions added yet.</EmptyHint>}
      {items.map((x, i) => (
        <EntryBlock key={i} label={`Position ${i + 1}`} onRemove={() => remove(i)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Organization" value={x.organization} onChange={(v) => patch(i, { organization: v })} placeholder="Acme Corp" />
            <Field label="Role" value={x.role} onChange={(v) => patch(i, { role: v })} placeholder="Software Engineer" />
            <Field label="Location" value={x.location ?? ""} onChange={(v) => patch(i, { location: v })} />
            <Field label="Dates" value={x.dates ?? ""} onChange={(v) => patch(i, { dates: v })} placeholder="Jun 2024 to Present" />
          </div>
          <StringListEditor label="Bullets" items={x.bullets} onChange={(v) => patch(i, { bullets: v })} addLabel="Add bullet" multiline placeholder="Built X that did Y, resulting in Z" />
        </EntryBlock>
      ))}
    </SectionCard>
  );
}
