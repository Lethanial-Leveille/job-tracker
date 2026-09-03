// Contact section: a flat block of fields (no repeatable entries, so no Add).
// Controlled slice — owns no state; the shell passes the Contact and a setter.
// `patch` merges one changed field into a new object (immutable update).

import type { Contact } from "../../lib/types";
import { Field } from "../ui/Field";
import { SectionCard } from "../ui/SectionCard";

interface Props {
  value: Contact;
  onChange: (value: Contact) => void;
}

export function ContactFields({ value, onChange }: Props) {
  const patch = (changes: Partial<Contact>) => onChange({ ...value, ...changes });

  return (
    <SectionCard
      title="Contact"
      description="How employers reach you. Your name is the only required field."
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Full name" value={value.name} onChange={(v) => patch({ name: v })} placeholder="Jane Doe" />
        <Field label="Email" type="email" value={value.email ?? ""} onChange={(v) => patch({ email: v })} placeholder="jane@example.com" />
        <Field label="Phone" value={value.phone ?? ""} onChange={(v) => patch({ phone: v })} />
        <Field label="Location" value={value.location ?? ""} onChange={(v) => patch({ location: v })} placeholder="City, State" />
        <Field label="LinkedIn" value={value.linkedin ?? ""} onChange={(v) => patch({ linkedin: v })} />
        <Field label="GitHub" value={value.github ?? ""} onChange={(v) => patch({ github: v })} />
        <Field label="Website" value={value.website ?? ""} onChange={(v) => patch({ website: v })} />
      </div>

      {/* Never printed on the resume. Postings routinely require this and a
          resume has no other place to say it, so requirement checks can only
          answer honestly once it is filled in. */}
      <div className="mt-3">
        <Field
          label="Work authorization (not printed on your resume)"
          value={value.work_authorization ?? ""}
          onChange={(v) => patch({ work_authorization: v })}
          placeholder="US citizen, no sponsorship required"
        />
      </div>
    </SectionCard>
  );
}
