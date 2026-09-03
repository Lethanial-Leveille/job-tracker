import type { Application } from "../../lib/types";
import { normalizeOrganization } from "../../lib/dedupe";

// Grouping the pipeline by employer, for the case of several applications to
// one company.
//
// This is a RENDERING concern only — there is no organizations table and no
// foreign key. `organization` is still a plain string on each row. A real table
// is the correct end state (it is what the sidebar's greyed-out "Organizations"
// item is a placeholder for), but it costs a migration, a backfill, and a merge
// UI, and none of that is earned until company-level data (contacts, notes)
// actually exists. normalizeOrganization is deliberately reused from the
// duplicate checker so that, when the real table does arrive, the function that
// groups here is the same one that backfills it.

export interface OrganizationGroup {
  key: string; // the normalized comparison key
  label: string; // the spelling to display
  applications: Application[];
}

// The soonest deadline in a set, or null when none of them have one.
function soonestDeadline(applications: Application[]): string | null {
  let soonest: string | null = null;
  for (const app of applications) {
    if (app.deadline === null) continue;
    if (soonest === null || app.deadline < soonest) soonest = app.deadline;
  }
  return soonest;
}

// Which spelling of the name to show. Companies name themselves inconsistently
// across job boards, so the group holds "Google", "Google LLC", and "Google,
// Inc." at once. Most frequent wins; ties go to the shortest, which is nearly
// always the clean human name rather than the legal one.
function pickLabel(names: string[]): string {
  const counts = new Map<string, number>();
  for (const name of names) counts.set(name, (counts.get(name) ?? 0) + 1);

  let best = names[0];
  let bestCount = 0;
  for (const [name, count] of counts) {
    if (count > bestCount || (count === bestCount && name.length < best.length)) {
      best = name;
      bestCount = count;
    }
  }
  return best;
}

// Group by employer, preserving the incoming order of rows WITHIN each group
// (the caller has already sorted by deadline).
//
// Groups themselves are ordered by their soonest deadline, nulls last. Without
// that, turning grouping on would destroy the list's whole organizing idea —
// "what is due next" — and replace it with alphabetical trivia. This way
// urgency survives at the group level.
export function groupByOrganization(
  applications: Application[],
): OrganizationGroup[] {
  const buckets = new Map<string, Application[]>();

  for (const app of applications) {
    // A name that is entirely legal-suffix noise normalizes to "". Falling back
    // to the raw name keeps it in its own group instead of collapsing every
    // such row together.
    const key = normalizeOrganization(app.organization) || app.organization.toLowerCase();
    const bucket = buckets.get(key);
    if (bucket) bucket.push(app);
    else buckets.set(key, [app]);
  }

  const groups: OrganizationGroup[] = [...buckets.entries()].map(
    ([key, apps]) => ({
      key,
      label: pickLabel(apps.map((a) => a.organization)),
      applications: apps,
    }),
  );

  return groups.sort((a, b) => {
    const left = soonestDeadline(a.applications);
    const right = soonestDeadline(b.applications);
    if (left === right) return a.label.localeCompare(b.label);
    if (left === null) return 1;
    if (right === null) return -1;
    return left < right ? -1 : 1;
  });
}
