import { describe, expect, it } from "vitest";
import { groupDiscoveries } from "./groupDiscoveries";
import type { DiscoveredJob } from "../../lib/types";

// Grouping, not dropping. Two postings that look alike are sometimes genuinely
// different roles, so everything stays reachable — the point is a shorter list,
// not a smaller one.

function job(organization: string, role_or_program: string, id = role_or_program): DiscoveredJob {
  return {
    id,
    source: "simplify",
    organization,
    role_or_program,
    posting_url: `https://x/${id}`,
    location: null,
    posted_at: null,
    state: "pending",
    target_company_id: null,
    role_family: null,
    possible_application_ids: null,
    eligibility: null,
    fit_score: null,
    fit_report: null,
    run_id: null,
    enriched_at: null,
    application_id: null,
    created_at: "2026-09-10T00:00:00Z",
  };
}

describe("groupDiscoveries", () => {
  it("folds a company's near-identical postings into one row", () => {
    // The real case: Booz Allen posts the same role three ways, per programme.
    const groups = groupDiscoveries([
      job("Booz Allen", "Software Developer Intern"),
      job("Booz Allen", "Software Developer Intern - Summer Games"),
      job("Booz Allen", "Software Developer Intern - University"),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].others).toHaveLength(2);
  });

  it("keeps genuinely different roles at one company apart", () => {
    const groups = groupDiscoveries([
      job("Stripe", "Software Engineer Intern"),
      job("Stripe", "Product Design Intern"),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("does not group the same title across different companies", () => {
    const groups = groupDiscoveries([
      job("Stripe", "Software Engineer Intern", "a"),
      job("Rivian", "Software Engineer Intern", "b"),
    ]);

    expect(groups).toHaveLength(2);
  });

  it("treats a company's legal suffixes as the same employer", () => {
    // "Google" and "Google LLC" are one company, which is exactly what
    // normalizeOrganization exists for.
    const groups = groupDiscoveries([
      job("Google", "Software Engineer Intern", "a"),
      job("Google LLC", "Software Engineer Intern", "b"),
    ]);

    expect(groups).toHaveLength(1);
  });

  it("leads with the first one, which is the best scoring", () => {
    // The server sorts by fit before this runs, so position carries meaning and
    // folding must never promote a worse match over a better one.
    const groups = groupDiscoveries([
      job("Acme", "Software Engineer Intern", "best"),
      job("Acme", "Software Engineer Intern - Summer", "worse"),
    ]);

    expect(groups[0].lead.id).toBe("best");
  });

  it("never loses a posting", () => {
    // The whole reason this groups rather than filters: a quietly deleted row
    // is a job you wanted with no way to notice it went.
    const input = [
      job("Acme", "Software Engineer Intern", "a"),
      job("Acme", "Software Engineer Intern - Summer", "b"),
      job("Beta", "Backend Intern", "c"),
    ];

    const groups = groupDiscoveries(input);
    const seen = groups.flatMap((g) => [g.lead, ...g.others]);

    expect(seen).toHaveLength(input.length);
  });

  it("does not collapse companies whose names are all noise", () => {
    // normalizeOrganization returns "" for a name made entirely of legal
    // suffixes, and grouping on that would merge unrelated employers.
    const groups = groupDiscoveries([
      job("The Inc", "Software Engineer Intern", "a"),
      job("LLC", "Software Engineer Intern", "b"),
    ]);

    expect(groups).toHaveLength(2);
  });
});
