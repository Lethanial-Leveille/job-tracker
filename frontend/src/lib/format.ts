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
export function statusLabel(status: ApplicationStatus): string {
  const spaced = status.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export type Urgency = "overdue" | "soon" | "normal";

export interface DeadlineDisplay {
  date: string; // "Jul 14"
  relative: string; // "Tomorrow", "in 3 days", "5 days ago"
  urgency: Urgency;
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

  return { date, relative, urgency };
}
