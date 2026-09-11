import { normalizeOrganization, roleSimilarity } from "../../lib/dedupe";
import type { DiscoveredJob } from "../../lib/types";

// Collapse near-identical postings from one employer into a single row.
//
// The feed carries a lot of these: 159 near-identical pairs in one pull. Booz
// Allen posts "Software Developer Intern", "Software Developer Intern - Summer
// Games" and "Software Developer Intern - University" as separate listings, and
// Mastercard posts "Data Scientist Intern" alongside "Data Scientist Intern -
// Summer 2027". They are usually the same job posted per location or per
// programme, and read as noise when the list is already three hundred long.
//
// Grouped rather than DROPPED, deliberately. Two postings that look alike are
// sometimes genuinely different roles, and a filter that quietly deleted one
// would be hiding a job you wanted with no way to notice. Everything stays
// reachable behind one line.
//
// The comparison reuses lib/dedupe.ts, the same functions the add screen uses
// to warn about a duplicate and the same logic the backend has ported to
// Python. Three copies of "are these the same job" that disagree would be worse
// than none.

export interface DiscoveryGroup {
  // The one shown by default: the first in the already-sorted list, which means
  // the best-scoring of the set, since sorting happens server-side before this.
  lead: DiscoveredJob;
  // Everything else that looked like it. Empty for the normal case.
  others: DiscoveredJob[];
}

// How alike two titles must be to collapse. Higher than the 0.7 the add screen
// warns at, because the cost is different: a warning you can dismiss can afford
// to be wrong, where folding a row away should only happen when the two are
// plainly the same posting.
const SAME_ENOUGH = 0.85;

export function groupDiscoveries(jobs: DiscoveredJob[]): DiscoveryGroup[] {
  const groups: DiscoveryGroup[] = [];

  for (const job of jobs) {
    const org = normalizeOrganization(job.organization);
    // Only ever folds into a group already established, so the leader is
    // whichever came first in the sorted list — the best match of the set.
    const into = groups.find(
      (group) =>
        // An employer with no usable name matches nothing rather than
        // everything: normalizeOrganization returns "" for a name that is all
        // noise, and grouping on that would collapse unrelated companies.
        org !== "" &&
        normalizeOrganization(group.lead.organization) === org &&
        roleSimilarity(group.lead.role_or_program, job.role_or_program) >= SAME_ENOUGH,
    );
    if (into) {
      into.others.push(job);
    } else {
      groups.push({ lead: job, others: [] });
    }
  }

  return groups;
}
