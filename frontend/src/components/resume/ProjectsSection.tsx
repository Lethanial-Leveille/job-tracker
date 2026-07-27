// Projects section: a repeatable list of projects, each with tools, links, and a
// bullet bank. Controlled slice, same immutable-update pattern. tools and links
// are short single-line lists; bullets are multiline.

import type { Project } from "../../lib/types";
import { Field } from "../ui/Field";
import { StringListEditor } from "../ui/StringListEditor";
import { EmptyHint, EntryBlock, SectionCard } from "../ui/SectionCard";

function blankProject(): Project {
  return { name: "", tools: [], links: [], dates: "", bullets: [] };
}

interface Props {
  items: Project[];
  onChange: (items: Project[]) => void;
}

export function ProjectsSection({ items, onChange }: Props) {
  const patch = (i: number, changes: Partial<Project>) =>
    onChange(items.map((p, idx) => (idx === i ? { ...p, ...changes } : p)));
  const add = () => onChange([...items, blankProject()]);
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <SectionCard
      title="Projects"
      description="Personal or academic projects. Keep every bullet; tailoring selects per application."
      onAdd={add}
      addLabel="Add project"
    >
      {items.length === 0 && <EmptyHint>No projects added yet.</EmptyHint>}
      {items.map((p, i) => (
        <EntryBlock key={i} label={`Project ${i + 1}`} onRemove={() => remove(i)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name" value={p.name} onChange={(v) => patch(i, { name: v })} placeholder="M.I.L.E.S." />
            <Field label="Dates" value={p.dates ?? ""} onChange={(v) => patch(i, { dates: v })} />
          </div>
          <StringListEditor label="Tools" items={p.tools} onChange={(v) => patch(i, { tools: v })} addLabel="Add tool" placeholder="Python" />
          <StringListEditor label="Links" items={p.links} onChange={(v) => patch(i, { links: v })} addLabel="Add link" placeholder="github.com/…" />
          <StringListEditor label="Bullets" items={p.bullets} onChange={(v) => patch(i, { bullets: v })} addLabel="Add bullet" multiline placeholder="Built X that did Y, resulting in Z" />
        </EntryBlock>
      ))}
    </SectionCard>
  );
}
