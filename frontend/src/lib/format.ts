// Display formatters. These turn raw API values into what the table shows.
// Keeping them here (not inline in components) means the label mappings are
// testable and consistent everywhere.

import type { ApplicationStatus } from "./types";

// Two-letter avatar monogram from an org name: first letters of the first two
// words, or the first two letters of a single word.
export function monogram(organization: string): string {
  const words = organization.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

// Humanize a status enum into sentence case: "technical_interview" ->
// "Technical interview". We show the real granular status, never a lossy bucket.
// Most values read fine as "underscores to spaces, then capitalize". A few are
// jargon that never said what it meant: "Phone screen" doesn't tell you who is
// on the call or why (it's a recruiter, checking fit and logistics), and
// "Discovered" is a strange word for a job you saved but haven't applied to.
//
// These are DISPLAY names only — the stored values are untouched, so relabeling
// costs nothing and is reversible.
const STATUS_LABELS: Partial<Record<ApplicationStatus, string>> = {
  discovered: "Saved",
  phone_screen: "Recruiter screen",
  // Distinct from a recruiter screen: this one is a recruiter reaching out to
  // you, not a call you earned by applying.
  recruiter_engaged: "Recruiter reached out",
  onsite: "Final round",
};

export function statusLabel(status: ApplicationStatus): string {
  const override = STATUS_LABELS[status];
  if (override) return override;
  const spaced = status.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export type Urgency = "overdue" | "soon" | "normal";

export interface DeadlineDisplay {
  date: string; // "Jul 14"
  relative: string; // "Tomorrow", "in 3 days", "5 days ago"
  urgency: Urgency;
  days: number; // whole days until; negative once it has passed
}

// Turn an ISO date string into an absolute label plus a relative one. Date-only
// math (no time-of-day) so a deadline never flips a day due to timezones.
export function formatDeadline(
  iso: string | null,
  now: Date = new Date(),
): DeadlineDisplay | null {
  if (!iso) return null;

  const [y, m, d] = iso.split("-").map(Number);
  const due = new Date(y, m - 1, d);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const MS_PER_DAY = 24 * 60 * 60 * 1000;
  const days = Math.round((due.getTime() - today.getTime()) / MS_PER_DAY);

  const date = due.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  let relative: string;
  if (days === 0) relative = "Today";
  else if (days === 1) relative = "Tomorrow";
  else if (days === -1) relative = "Yesterday";
  else if (days > 1) relative = `in ${days} days`;
  else relative = `${Math.abs(days)} days ago`;

  const urgency: Urgency = days < 0 ? "overdue" : days <= 3 ? "soon" : "normal";

  return { date, relative, urgency, days };
}

// Whole days since an ISO timestamp. Used for the "quiet Nd" counter that
// replaces the deadline once an application is out the door: the deadline stops
// being actionable the moment you apply, but how long you have been waiting
// never stops mattering.
export function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

// "Sep 2" from a full ISO timestamp. formatDeadline cannot do this: it parses a
// date-only string on purpose (so a deadline never shifts a day across
// timezones), and applied_at is a real timestamp.
export function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
