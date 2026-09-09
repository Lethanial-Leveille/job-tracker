// Which graduation date to print, suggested from the posting itself.
//
// Lee can honestly claim two graduation dates (94 credit hours against a
// 128-credit degree), and which one helps depends entirely on what the posting
// requires: a "rising junior" role wants the earlier date, a program that only
// takes first and second years wants the later one. Getting it backwards is not
// a wasted shot but an active disqualification in both directions.
//
// The result carries a `basis` saying how it was reached, and the caller uses
// that to decide whether to APPLY it or merely suggest it:
//
//   "standing" — the posting names a class standing outright. The caller
//     pre-selects the checkbox and says so. Pre-selecting a VISIBLE control
//     with the matched phrase shown is not a silent flip; it is still reviewed
//     before anything downloads.
//   "year" — inferred from a graduation year, which already involves a guess.
//     Suggest only, never apply.
//
// The original rule here was "hint, never a switch", on the grounds that a wrong
// automatic flip prints a date Lee did not choose. That still holds for the
// inferred path, which is why the split exists rather than a blanket auto-apply.
//
// Pure and synchronous, running on data already in memory. No network, no
// parse call, no backend change.

import type { Application } from "./types";

export type GradVariant = "primary" | "alternate";

export interface GradHint {
  // "primary" = the earlier date (further along). "alternate" = the later one.
  suggest: GradVariant;
  // How the suggestion was reached, which decides whether it may act on its own.
  // "standing" — the posting names a class standing ("open to rising
  //   sophomores"). That is a direct statement of eligibility, so it is safe to
  //   APPLY, not merely suggest.
  // "year" — inferred from a graduation year in a sentence about graduating.
  //   That path already guesses: a range like "December 2028 - June 2029" is
  //   read by taking the maximum. A guess may suggest; it may not decide.
  basis: "standing" | "year";
  // The exact phrase from the posting that triggered this, shown to the user.
  // A suggestion you cannot check is a suggestion you either obey blindly or
  // ignore entirely, and both are worse than no suggestion.
  evidence: string;
}

// Phrases naming a class standing. Checked BEFORE graduation years because they
// are the direct statement of eligibility; a year range is often a softer hint
// sitting alongside one of these.
const EARLIER: readonly string[] = [
  "rising junior",
  "rising senior",
  "junior standing",
  "senior standing",
  "juniors and seniors",
  "third year",
  "fourth year",
  "penultimate year",
  "final year",
];

const LATER: readonly string[] = [
  "rising sophomore",
  "sophomore standing",
  "first year",
  "second year",
  "freshmen and sophomores",
  "underclassmen",
  "early career discovery",
];

// A graduation year only means something next to a word about graduating, so
// this requires both rather than matching any stray 2029 (a posting can mention
// a program start date, a fiscal year, or a product roadmap).
const GRAD_CONTEXT = /(graduat|commencement|degree completion|class of)/i;
const YEAR = /\b(20(2[5-9]|3[0-2]))\b/g;

// Lee's two dates. Anything at or before the earlier one argues for printing it;
// anything strictly after argues for the later.
const EARLIER_YEAR = 2028;

function sentencesOf(text: string): string[] {
  return text
    .split(/(?<=[.!?;\n])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

// Trim a matched sentence to something that fits in a line of UI without
// dropping the part that matters.
function excerpt(sentence: string, limit = 120): string {
  const flat = sentence.replace(/\s+/g, " ").trim();
  return flat.length <= limit ? flat : `${flat.slice(0, limit - 1)}…`;
}

/**
 * Suggest a graduation-date variant from a posting, or null when it says
 * nothing about eligibility. Null is the common and correct answer: most
 * postings are silent, and silence means the default (the earlier date) stands.
 */
export function gradDateHint(application: Application): GradHint | null {
  const sources = [
    ...(application.jd_parsed?.key_requirements ?? []),
    ...(application.jd_parsed?.preferred_qualifications ?? []),
    ...sentencesOf(application.jd_text ?? ""),
  ];

  // Pass 1: an explicit class standing wins outright.
  for (const raw of sources) {
    const lower = raw.toLowerCase();
    for (const phrase of LATER) {
      if (lower.includes(phrase))
        return { suggest: "alternate", basis: "standing", evidence: excerpt(raw) };
    }
    for (const phrase of EARLIER) {
      if (lower.includes(phrase))
        return { suggest: "primary", basis: "standing", evidence: excerpt(raw) };
    }
  }

  // Pass 2: a graduation year, but only where the sentence is actually about
  // graduating. A window like "December 2028 - June 2029" includes a year past
  // the earlier date, which is the case where the later date is safe AND buys
  // eligibility, so the maximum is what decides it.
  for (const raw of sources) {
    if (!GRAD_CONTEXT.test(raw)) continue;
    const years = [...raw.matchAll(YEAR)].map((m) => Number(m[1]));
    if (years.length === 0) continue;
    const latest = Math.max(...years);
    return {
      suggest: latest > EARLIER_YEAR ? "alternate" : "primary",
      basis: "year",
      evidence: excerpt(raw),
    };
  }

  return null;
}
