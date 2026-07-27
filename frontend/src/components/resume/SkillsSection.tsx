// Skills section: a repeatable list of skill groups, each a category plus its
// items (e.g. "Languages": Python, C++). Controlled slice, same immutable-update
// pattern as the other repeatable sections.

import type { SkillGroup } from "../../lib/types";
import { Field } from "../ui/Field";
import { StringListEditor } from "../ui/StringListEditor";
import { EmptyHint, EntryBlock, SectionCard } from "../ui/SectionCard";

function blankSkillGroup(): SkillGroup {
  return { category: "", items: [] };
}

interface Props {
  items: SkillGroup[];
  onChange: (items: SkillGroup[]) => void;
}

export function SkillsSection({ items, onChange }: Props) {
  const patch = (i: number, changes: Partial<SkillGroup>) =>
    onChange(items.map((g, idx) => (idx === i ? { ...g, ...changes } : g)));
  const add = () => onChange([...items, blankSkillGroup()]);
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <SectionCard
      title="Skills"
      description="Group related skills under a category label."
      onAdd={add}
      addLabel="Add group"
    >
      {items.length === 0 && <EmptyHint>No skill groups added yet.</EmptyHint>}
      {items.map((g, i) => (
        <EntryBlock key={i} label={`Group ${i + 1}`} onRemove={() => remove(i)}>
          <Field label="Category" value={g.category} onChange={(v) => patch(i, { category: v })} placeholder="Languages" />
          <StringListEditor label="Items" items={g.items} onChange={(v) => patch(i, { items: v })} addLabel="Add skill" placeholder="Python" />
        </EntryBlock>
      ))}
    </SectionCard>
  );
}
