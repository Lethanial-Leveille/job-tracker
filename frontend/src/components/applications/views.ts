// Saved views: three named questions over the list you already have.
//
// Entirely client-side. No schema, no endpoint, no stored "view" record — each
// is a predicate over data the page has already fetched, so adding one costs a
// function and removing one leaves nothing behind. That is the whole reason
// they are worth shipping now rather than after a backend design.
//
// They live in the URL (`/applications?view=in_process`) rather than in state,
// which is the pattern App.tsx already sets ("the URL is the source of truth").
// It also means the sidebar can be plain links: no lifting state up through
// AppShell just so a nav item can filter a route below it.

import type { Application } from "../../lib/types";
import { daysSince, formatDeadline } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";

export type ViewKey = "closing" | "in_process" | "quiet";

export interface SavedView {
  key: ViewKey;
  label: string;
  matches: (app: Application) => boolean;
}

// Matches DeadlineCell's and sections.ts's threshold. If these drifted, the view
// would disagree with the band and the brightness on the same row.
const URGENT_DAYS = 4;
// Three weeks without a reply is when a follow-up is worth sending.
const QUIET_DAYS = 12;

// The stages where something is actively happening and you are the one being
// evaluated. `offer` is in here because an unanswered offer is very much in
// process, and it is why this view's dot is the purple one.
const IN_PROCESS = ["assessment", "phone_screen", "technical_interview", "offer"];

export const SAVED_VIEWS: SavedView[] = [
  {
    key: "closing",
    label: "Closing in 4 days",
    matches: (app) => {
      if (!isPreSubmit(app.status)) return false;
      const days = formatDeadline(app.deadline)?.days;
      return days !== undefined && days <= URGENT_DAYS;
    },
  },
  {
    key: "in_process",
    label: "In process",
    matches: (app) => IN_PROCESS.includes(app.status),
  },
  {
    key: "quiet",
    label: `Quiet ${QUIET_DAYS}+ days`,
    // Applied, not closed, and no news since. A row with no applied_at cannot
    // be counted from, so it is not quiet — it is unknown, which is different.
    matches: (app) =>
      !isPreSubmit(app.status) &&
      !isClosed(app.status) &&
      app.applied_at !== null &&
      daysSince(app.applied_at) >= QUIET_DAYS,
  },
];

export function findView(key: string | null): SavedView | null {
  if (!key) return null;
  return SAVED_VIEWS.find((v) => v.key === key) ?? null;
}

export function countFor(view: SavedView, applications: Application[]): number {
  return applications.filter(view.matches).length;
}
