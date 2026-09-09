import type { ApplicationStatus } from "../../lib/types";

// Which statuses the UI actually offers, as opposed to which ones the database
// can store. The backend enum still holds all fourteen (models/application.py)
// and we deliberately do NOT delete members from it: existing rows carry those
// values, and a native Postgres enum needs an ALTER TYPE migration to change
// (docs/decisions.md, the v3 enum gotcha). So the trimming happens here, in the
// UI, where it costs nothing to undo.

// The short list: the stages an internship application actually passes through
// often enough to be worth one click. This is what the row menu shows.
//
// These are a VOCABULARY, not a sequence. Real funnels vary — an assessment can
// come before or after a recruiter call, and some companies skip the call
// entirely — so nothing validates transitions. The order here is only the order
// they appear in the menu; the status history records what actually happened.
export const QUICK_STATUSES: ApplicationStatus[] = [
  "discovered",
  "applied",
  "assessment",
  "phone_screen",
  "technical_interview",
  "offer",
  "rejected",
];

// Every value the backend accepts, in pipeline order. The edit form shows the
// ones missing from QUICK_STATUSES behind a "More statuses" disclosure.
export const ALL_STATUSES: ApplicationStatus[] = [
  "discovered",
  "drafting",
  "ready",
  "applied",
  "assessment",
  "recruiter_engaged",
  "phone_screen",
  "technical_interview",
  "onsite",
  "offer",
  "accepted",
  "declined",
  "rejected",
  "ghosted",
  "missed_deadline",
];

export const MORE_STATUSES: ApplicationStatus[] = ALL_STATUSES.filter(
  (status) => !QUICK_STATUSES.includes(status),
);

// The pre-submit stages: found it, drafting for it, ready to send. Everything
// from `applied` onward means it went out the door, however it ended.
//
// This lives here rather than in the toolbar that first needed it, because it
// describes the STATUS VALUES, not a filter control. Two unrelated places ask
// the same question now (the "Not applied" filter, and whether the tailor tab
// should offer "Mark as applied"), and they must not drift.
const PRE_SUBMIT: ApplicationStatus[] = ["discovered", "drafting", "ready"];

export function isPreSubmit(status: ApplicationStatus): boolean {
  return PRE_SUBMIT.includes(status);
}

// Went out the door, however it ended. NOT simply the negation of isPreSubmit:
// `missed_deadline` is in neither set, because that row was never applied to and
// never can be. It is the one status where a passed deadline is the whole point
// of the row rather than noise, so it must keep its date.
//
// Mirrors the SUBMITTED set in backend/scripts/backfill_deadlines.py; the two
// answer the same question and must not drift.
const SUBMITTED: ApplicationStatus[] = [
  "applied",
  "assessment",
  "recruiter_engaged",
  "phone_screen",
  "technical_interview",
  "onsite",
  "offer",
  "accepted",
  "declined",
  "rejected",
  "ghosted",
];

export function isSubmitted(status: ApplicationStatus): boolean {
  return SUBMITTED.includes(status);
}

// The options for one row's status menu.
//
// A row can be sitting on a status that is not in the short list (an older row
// marked "Ghosted", say). A <select> whose value matches none of its options
// renders blank and silently reports the first option instead, so the current
// status is prepended when it would otherwise be missing. The menu is then
// honest about where the row is, and picking nothing changes nothing.
export function menuStatuses(current: ApplicationStatus): ApplicationStatus[] {
  return QUICK_STATUSES.includes(current)
    ? QUICK_STATUSES
    : [current, ...QUICK_STATUSES];
}
