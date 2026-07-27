// Education section: a repeatable list of schools. Controlled slice — receives
// the Education[] and a setter; every edit produces a new array (immutable).
// `patch` updates one field of one entry; add/remove append/filter whole entries.

import type { Education } from "../../lib/types";
import { Field } from "../ui/Field";
import { StringListEditor } from "../ui/StringListEditor";
import { EmptyHint, EntryBlock, SectionCard } from "../ui/SectionCard";

function blankEducation(): Education {
  return { institution: "", degree: "", location: "", dates: "", gpa: "", honors: [], coursework: [] };
}

interface Props {
  items: Education[];
  onChange: (items: Education[]) => void;
}

export function EducationSection({ items, onChange }: Props) {
  const patch = (i: number, changes: Partial<Education>) =>
    onChange(items.map((e, idx) => (idx === i ? { ...e, ...changes } : e)));
  const add = () => onChange([...items, blankEducation()]);
  const remove = (i: number) => onChange(items.filter((_, idx) => idx !== i));

  return (
    <SectionCard
      title="Education"
      description="Schools and degrees. GPA and coursework show on student resumes; they're hidden on professional ones."
      onAdd={add}
      addLabel="Add school"
    >
      {items.length === 0 && <EmptyHint>No schools added yet.</EmptyHint>}
      {items.map((e, i) => (
        <EntryBlock key={i} label={`School ${i + 1}`} onRemove={() => remove(i)}>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Institution" value={e.institution} onChange={(v) => patch(i, { institution: v })} placeholder="University of Florida" />
            <Field label="Degree" value={e.degree} onChange={(v) => patch(i, { degree: v })} placeholder="B.S. Computer Engineering" />
            <Field label="Location" value={e.location ?? ""} onChange={(v) => patch(i, { location: v })} />
            <Field label="Dates" value={e.dates ?? ""} onChange={(v) => patch(i, { dates: v })} placeholder="Expected May 2029" />
            <Field label="GPA" value={e.gpa ?? ""} onChange={(v) => patch(i, { gpa: v })} placeholder="3.8 / 4.0" />
          </div>
          <StringListEditor label="Honors" items={e.honors} onChange={(v) => patch(i, { honors: v })} addLabel="Add honor" placeholder="Dean's List" />
          <StringListEditor label="Relevant coursework" items={e.coursework} onChange={(v) => patch(i, { coursework: v })} addLabel="Add course" />
        </EntryBlock>
      ))}
    </SectionCard>
  );
}
