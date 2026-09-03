// Duplicate detection for the add flow.
//
// The point is to catch a re-add BEFORE spending a parse call on it. Every one
// of these functions is pure and synchronous, and they run against the
// applications list already held in memory by useApplications — no network, no
// API cost, no backend change.
//
// Everything here produces a WARNING, never a block. Reapplying to a role next
// cycle is a real thing you do, so the flow always offers "add anyway".

import type { Application } from "./types";

// --- URL matching -----------------------------------------------------------

// Query parameters that describe how you ARRIVED at a posting rather than which
// posting it is. Stripping these makes the same job shared two ways compare
// equal.
//
// This list is deliberately short. The tempting move is to drop every query
// param, and it is wrong: Greenhouse and Lever put the actual job id in the
// query string (`?gh_jid=4055123`), so a blanket strip would collapse every
// posting at a company into one and report constant false duplicates. Only
// known tracking keys are removed; anything unrecognized is treated as
// identifying and kept.
const TRACKING_PARAMS = new Set([
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "ref",
  "referer",
  "referrer",
  "refid",
  "source",
  "src",
  "gh_src", // Greenhouse SOURCE. Not gh_jid, which is the job id.
  "trk",
  "trackingid",
  "originalsubdomain",
]);

// Reduce a URL to a comparable key: scheme dropped, host lowercased and
// de-www'd, trailing slash removed, tracking params stripped, remaining params
// sorted so param order can't make two identical links look different, hash
// dropped. Returns null for empty input.
//
// A string that doesn't parse as a URL is not an error here — you may have
// pasted something half-typed — so it falls back to a trimmed, lowercased
// comparison rather than throwing.
export function normalizeUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;

  // new URL() demands a scheme, and you rarely type one.
  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;

  let url: URL;
  try {
    url = new URL(withScheme);
  } catch {
    return trimmed.toLowerCase();
  }

  const host = url.hostname.toLowerCase().replace(/^www\./, "");
  const path = url.pathname.replace(/\/+$/, "");

  const params = [...url.searchParams.entries()]
    .filter(([key]) => !TRACKING_PARAMS.has(key.toLowerCase()))
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([key, value]) => `${key}=${value}`);
  const query = params.length > 0 ? `?${params.join("&")}` : "";

  return `${host}${path}${query}`;
}

// The strong signal: you already have a row pointing at this exact posting.
export function findUrlMatch(
  applications: Application[],
  url: string,
): Application | null {
  const key = normalizeUrl(url);
  if (key === null) return null;
  return (
    applications.find((app) => normalizeUrl(app.posting_url) === key) ?? null
  );
}

// --- Organization and role matching -----------------------------------------

// Legal suffixes and articles that appear inconsistently in how a company names
// itself across job boards. "Google", "Google LLC", and "Google, Inc." are one
// employer.
const ORG_NOISE = new Set([
  "inc",
  "llc",
  "ltd",
  "limited",
  "corp",
  "corporation",
  "co",
  "company",
  "plc",
  "gmbh",
  "ag",
  "sa",
  "nv",
  "the",
]);

// A comparison key for an employer name. Also the function that a future
// organizations table would use to backfill itself, so it lives here rather
// than inline in a component.
export function normalizeOrganization(name: string): string {
  return name
    .toLowerCase()
    .replace(/[.,'’&]/g, "")
    .split(/[\s/|-]+/)
    .filter((word) => word !== "" && !ORG_NOISE.has(word))
    .join(" ");
}

// Words that appear in nearly every internship title and therefore carry no
// information about WHICH internship it is. Left in, "Software Engineer Intern,
// Summer 2027" and "Data Engineer Internship 2027" would look similar on the
// strength of "intern" and "2027" alone.
const ROLE_NOISE = new Set([
  "intern",
  "interns",
  "internship",
  "internships",
  "co-op",
  "coop",
  "summer",
  "fall",
  "winter",
  "spring",
  "student",
  "program",
  "the",
  "and",
  "of",
  "for",
  "a",
  "an",
  "i",
  "ii",
  "iii",
]);

// Collapse the endings that make the same word look like two: "engineering"
// and "engineer" both become "engine". Without this, "Software Engineer Intern"
// and "Software Engineering Internship" share no tokens at all and score zero,
// which is the single most common way one job gets titled on two boards.
//
// Each rule only fires if it leaves at least four characters, so short words are
// never mangled down to noise. This is deliberately not a real stemmer: it needs
// to be predictable enough to reason about when a warning looks wrong.
function stem(word: string): string {
  let out = word;
  const strip = (suffix: string) => {
    if (out.endsWith(suffix) && out.length - suffix.length >= 4) {
      out = out.slice(0, -suffix.length);
    }
  };
  strip("ing"); // engineering -> engineer
  strip("ers"); // engineers   -> engine
  strip("er"); //  engineer    -> engine
  if (!out.endsWith("ss")) strip("s"); // systems -> system, business stays
  return out;
}

function roleTokens(role: string): Set<string> {
  return new Set(
    role
      .toLowerCase()
      .replace(/[.,'’&()]/g, "")
      .split(/[\s/|,-]+/)
      .filter(
        (word) =>
          word !== "" && !ROLE_NOISE.has(word) && !/^(19|20)\d{2}$/.test(word),
      )
      .map(stem),
  );
}

// How much two titles overlap, as a fraction of the SHORTER one's meaningful
// words. Shorter, not the union, on purpose: "Software Engineer Intern" and
// "Software Engineer Intern, Machine Learning Platform" are plausibly the same
// posting written out at different lengths, and measuring against the union
// would score that pair low precisely because one side is more detailed.
function roleSimilarity(a: string, b: string): number {
  const left = roleTokens(a);
  const right = roleTokens(b);
  if (left.size === 0 || right.size === 0) return 0;
  let shared = 0;
  for (const token of left) {
    if (right.has(token)) shared += 1;
  }
  return shared / Math.min(left.size, right.size);
}

// Every application already tracked at one employer, regardless of role.
//
// The weakest signal of the three, and the one that catches what the other two
// structurally cannot. Two real cases from live use:
//   - You paste the URL of a later STEP in an application flow rather than the
//     posting itself. That is a genuinely different page, so no amount of URL
//     normalization will match it.
//   - The parser cannot find a job title, so there is nothing for the title
//     similarity check to compare against and it scores zero.
// In both, "you already track 2 things at Arm" is still worth saying. It is
// shown as information, never as a duplicate warning — several roles at one
// company is normal, which is exactly why grouping exists.
export function findByOrganization(
  applications: Application[],
  organization: string,
): Application[] {
  const orgKey = normalizeOrganization(organization);
  if (orgKey === "") return [];
  return applications.filter(
    (app) => normalizeOrganization(app.organization) === orgKey,
  );
}

// The weaker signal, for the case the URL check structurally cannot catch: the
// same job posted to two different boards, so two different links. Runs after
// parsing, since the organization and title come from the parser.
//
// 0.7 is a deliberately cautious threshold. A missed warning costs you a
// duplicate row you can delete; a false warning on every add trains you to
// dismiss the thing without reading it, which is worse.
export function findSimilarPosting(
  applications: Application[],
  organization: string,
  role: string,
): Application | null {
  const orgKey = normalizeOrganization(organization);
  if (orgKey === "") return null;

  return (
    applications.find(
      (app) =>
        normalizeOrganization(app.organization) === orgKey &&
        roleSimilarity(app.role_or_program, role) >= 0.7,
    ) ?? null
  );
}
