import type { DiscoveredJob } from "../../lib/types";

// Narrowing the inbox, which is a different problem from ordering it.
//
// Sorting by fit means the top of the list is worth reading. It does nothing
// about the other two hundred and eighty rows still sitting there, and a list
// that long reads as a chore no matter what order it is in. These are the
// controls that make it shorter rather than better sorted.
//
// Every one of them is a predicate over data already on screen, so switching a
// filter costs nothing and can be undone instantly. Nothing here talks to the
// server, and nothing here is remembered — a filter that silently persisted
// across visits is how you conclude the feed stopped finding anything.

export interface DiscoveryFilters {
  // Free text over the employer and the title. The one control that answers a
  // question the others cannot: "is Rivian in here anywhere", which on a list
  // of two hundred and forty is otherwise a scroll and a squint.
  query: string;
  // Only what the most recent pull found. The single most useful one on a
  // second visit: you have already read everything else.
  newOnly: boolean;
  // Minimum fit, 0 for no minimum. Unscored rows are kept at every level except
  // the highest — unknown is not a bad match, and burying every posting from a
  // site that needs a browser would hide real jobs for a reason that is about
  // the website rather than the job.
  minFit: number;
  // Only companies on your watchlist. You chose those, which is a stronger
  // statement than any score.
  watchlistOnly: boolean;
}

export const NO_FILTERS: DiscoveryFilters = {
  query: "",
  newOnly: false,
  minFit: 0,
  watchlistOnly: false,
};

export function applyFilters(
  jobs: DiscoveredJob[],
  filters: DiscoveryFilters,
  latestRunId: string | null,
): DiscoveredJob[] {
  // Matched on a lowercased substring rather than anything cleverer. A fuzzy
  // match here would be worse, not better: you already know the company name
  // you are looking for, and a search that returns near-misses for an exact
  // query reads as broken.
  const query = filters.query.trim().toLowerCase();

  return jobs.filter((job) => {
    if (query !== "") {
      // Employer AND title, because both are things you would search for — "is
      // Rivian in here" and "any embedded roles" are the same gesture.
      const haystack = `${job.organization} ${job.role_or_program}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (filters.newOnly && (latestRunId === null || job.run_id !== latestRunId)) {
      return false;
    }
    if (filters.watchlistOnly && job.target_company_id === null) return false;
    if (filters.minFit > 0) {
      // Unscored rows survive a minimum unless you ask for the strongest
      // matches only. At that point you are deliberately asking for certainty,
      // and "we could not read it" is not certainty.
      if (job.fit_score === null) return filters.minFit < 80;
      if (job.fit_score < filters.minFit) return false;
    }
    return true;
  });
}

// How many groups to show at once. Sized so a page is a sitting rather than a
// scroll: about fifteen decisions is roughly where attention goes, and a page
// you can finish is the difference between triaging and giving up.
export const PAGE_SIZE = 15;
