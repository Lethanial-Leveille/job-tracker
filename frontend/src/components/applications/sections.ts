// Urgency sectioning for the flat list.
//
// The list is sorted by deadline, which answers "what is due next" but not the
// question actually being asked every morning: "what needs me today". Those
// differ because a deadline stops mattering the moment you apply — 41 of 64 rows
// are already out the door, and they were interleaved with the ones still open.
//
// So the flat list is cut into bands by what you can DO about each row: a stage
// task due now, apply now, apply later, wait, done. Within a band the deadline order still holds.
//
// This replaces nothing when `grouped` is on: grouping by employer answers a
// different question and owns the list in that mode.

import type { Application } from "../../lib/types";
import { daysSince, formatDeadline } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";

export type SectionKey = "due" | "closing" | "open" | "in_flight" | "closed";

export interface Section {
  key: SectionKey;
  label: string;
  // A short line saying why the band exists. Shown next to the heading, muted.
  hint: string | null;
  applications: Application[];
}

// Inside four days is "act on this now", matching DeadlineCell's threshold so
// the band and the brightness of the date agree. If they drifted, a row could
// sit under "Closing this week" with a dim date.
const URGENT_DAYS = 4;

function daysUntilDeadline(app: Application): number | null {
  return formatDeadline(app.deadline)?.days ?? null;
}

function keyFor(app: Application): SectionKey {
  if (isClosed(app.status)) return "closed";
  if (!isPreSubmit(app.status)) {
    // Out the door, but an assessment or other stage task is due soon: that is
    // the most valuable thing on the list, so it leaves "In flight" and leads.
    const due = formatDeadline(app.next_step_due)?.days;
    return due !== undefined && due <= URGENT_DAYS ? "due" : "in_flight";
  }
  const days = daysUntilDeadline(app);
  return days !== null && days <= URGENT_DAYS ? "closing" : "open";
}

const ORDER: { key: SectionKey; label: string; hint: string | null }[] = [
  {
    key: "due",
    label: "Your move",
    hint: "a stage task due within 4 days",
  },
  {
    key: "closing",
    label: "Closing this week",
    hint: "not applied yet — act on these first",
  },
  { key: "open", label: "Open, further out", hint: null },
  {
    key: "in_flight",
    label: "In flight",
    hint: "deadline retired — counting silence instead",
  },
  { key: "closed", label: "Closed", hint: null },
];

/**
 * Split into urgency bands, preserving the incoming order inside each one.
 *
 * Empty bands are omitted entirely rather than rendered as a heading over
 * nothing: a "Closed" heading with no rows under it reads as a loading failure.
 */
export function sectionByUrgency(applications: Application[]): Section[] {
  const buckets = new Map<SectionKey, Application[]>();
  for (const app of applications) {
    const key = keyFor(app);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(app);
    else buckets.set(key, [app]);
  }

  // "In flight" sorts by descending silence instead of by deadline: the row you
  // have waited longest on is the one worth chasing, and its deadline is retired
  // so deadline order would be sorting on a value the row no longer shows.
  // Silence counts from the latest status change, matching DeadlineCell.
  const inFlight = buckets.get("in_flight");
  if (inFlight) {
    const quiet = (a: Application): number => {
      const since = a.last_status_at ?? a.applied_at;
      return since ? daysSince(since) : -1;
    };
    inFlight.sort((a, b) => quiet(b) - quiet(a));
  }

  // "Your move" sorts by which task is due first. ISO dates sort as strings.
  buckets
    .get("due")
    ?.sort((a, b) => (a.next_step_due ?? "").localeCompare(b.next_step_due ?? ""));

  return ORDER.filter((s) => (buckets.get(s.key)?.length ?? 0) > 0).map((s) => ({
    ...s,
    applications: buckets.get(s.key) ?? [],
  }));
}
