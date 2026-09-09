import type { ApplicationStatus } from "../../lib/types";
import { statusLabel } from "../../lib/format";

// A 6px dot and a plain word. The pill is gone.
//
// Why: a filled, bordered badge repeated on 41 consecutive rows carries no
// information. Every row looked equally loud, so the eye had nothing to catch
// on, and the column that should say "this one is moving" said "this is a
// table". The dot keeps the shape cue at a fraction of the weight, and the
// difference between stages is carried by BRIGHTNESS — which is the only
// urgency signal design.md allows, since the single accent is spent elsewhere.
//
// Four visual tiers, not fourteen:
//   early   — discovered. Present, clearly not started.
//   sent    — applied. Out the door, nothing happening yet.
//   live    — assessment / phone screen / interview. Something is happening.
//   closed  — rejected / ghosted / declined / missed. Hollow, and dimmed.
//   offer   — the one purple thing in the data, with the one permanent glow.
//
// One glowing dot in 64 rows is the entire point of the accent budget.

type Tier = "early" | "sent" | "live" | "closed" | "offer";

const TIER: Record<string, Tier> = {
  discovered: "early",
  drafting: "early",
  ready: "early",
  applied: "sent",
  assessment: "live",
  recruiter_engaged: "live",
  phone_screen: "live",
  technical_interview: "live",
  onsite: "live",
  offer: "offer",
  accepted: "offer",
  rejected: "closed",
  declined: "closed",
  ghosted: "closed",
  missed_deadline: "closed",
};

const DOT: Record<Tier, string> = {
  early: "bg-stage-early ring-1 ring-ink-spent",
  sent: "bg-stage-sent ring-1 ring-ink-3",
  live: "bg-stage-live ring-1 ring-stage-ring",
  closed: "bg-transparent ring-1 ring-stage-early",
  offer: "bg-accent-edge ring-1 ring-accent-text shadow-offer-dot",
};

const LABEL: Record<Tier, string> = {
  early: "text-ink-2",
  sent: "text-ink-2",
  live: "text-ink font-medium",
  closed: "text-ink-label",
  offer: "text-accent-soft font-semibold",
};

export function StatusBadge({ status }: { status: ApplicationStatus }) {
  const tier = TIER[status] ?? "sent";
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap text-[13px]">
      <span className={`size-1.5 shrink-0 rounded-full ${DOT[tier]}`} aria-hidden="true" />
      <span className={LABEL[tier]}>{statusLabel(status)}</span>
    </span>
  );
}
