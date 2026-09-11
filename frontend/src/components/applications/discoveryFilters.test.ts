import { describe, expect, it } from "vitest";
import { applyFilters, NO_FILTERS } from "./discoveryFilters";
import type { DiscoveredJob } from "../../lib/types";

function job(over: Partial<DiscoveredJob>): DiscoveredJob {
  return {
    id: "1",
    source: "simplify",
    organization: "Acme",
    role_or_program: "Software Engineer Intern",
    posting_url: "https://x/1",
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
    ...over,
  };
}

describe("applyFilters", () => {
  it("keeps everything by default", () => {
    const jobs = [job({ id: "a" }), job({ id: "b" })];
    expect(applyFilters(jobs, NO_FILTERS, null)).toHaveLength(2);
  });

  it("new only keeps what the latest pull found", () => {
    const jobs = [job({ id: "a", run_id: "r2" }), job({ id: "b", run_id: "r1" })];

    const out = applyFilters(jobs, { ...NO_FILTERS, newOnly: true }, "r2");

    expect(out.map((j) => j.id)).toEqual(["a"]);
  });

  it("new only shows nothing rather than everything when no run is known", () => {
    // The dangerous direction: falling back to "everything is new" would make
    // the filter look broken in exactly the situation it matters.
    const jobs = [job({ run_id: "r1" })];

    expect(applyFilters(jobs, { ...NO_FILTERS, newOnly: true }, null)).toHaveLength(0);
  });

  it("a minimum keeps unscored rows", () => {
    // Unknown is not a bad match. A posting on a site that needs a browser
    // cannot be scored, and burying it would hide a real job for a reason that
    // is about the website rather than the job.
    const jobs = [job({ id: "unscored" }), job({ id: "weak", fit_score: 20 })];

    const out = applyFilters(jobs, { ...NO_FILTERS, minFit: 60 }, null);

    expect(out.map((j) => j.id)).toEqual(["unscored"]);
  });

  it("asking for the strongest matches excludes the unscored", () => {
    // At that point you are deliberately asking for certainty, and "could not
    // be read" is not certainty.
    const jobs = [job({ id: "unscored" }), job({ id: "strong", fit_score: 90 })];

    const out = applyFilters(jobs, { ...NO_FILTERS, minFit: 80 }, null);

    expect(out.map((j) => j.id)).toEqual(["strong"]);
  });

  it("watchlist only keeps jobs from a company you chose", () => {
    const jobs = [job({ id: "board", target_company_id: "c1" }), job({ id: "feed" })];

    const out = applyFilters(jobs, { ...NO_FILTERS, watchlistOnly: true }, null);

    expect(out.map((j) => j.id)).toEqual(["board"]);
  });

  it("finds a company by name", () => {
    const jobs = [job({ id: "a", organization: "Rivian" }), job({ id: "b", organization: "Stripe" })];

    const out = applyFilters(jobs, { ...NO_FILTERS, query: "rivi" }, null);

    expect(out.map((j) => j.id)).toEqual(["a"]);
  });

  it("searches the title as well as the employer", () => {
    // "Is Rivian in here" and "any embedded roles" are the same gesture.
    const jobs = [
      job({ id: "a", role_or_program: "Embedded Systems Intern" }),
      job({ id: "b", role_or_program: "Backend Intern" }),
    ];

    const out = applyFilters(jobs, { ...NO_FILTERS, query: "embedded" }, null);

    expect(out.map((j) => j.id)).toEqual(["a"]);
  });

  it("ignores case and surrounding space", () => {
    const jobs = [job({ organization: "Rivian" })];

    expect(applyFilters(jobs, { ...NO_FILTERS, query: "  RIVIAN " }, null)).toHaveLength(1);
  });

  it("an empty search is not a filter", () => {
    const jobs = [job({ id: "a" }), job({ id: "b" })];

    expect(applyFilters(jobs, { ...NO_FILTERS, query: "   " }, null)).toHaveLength(2);
  });

  it("combines filters rather than picking one", () => {
    const jobs = [
      job({ id: "both", run_id: "r1", fit_score: 90 }),
      job({ id: "newOnly", run_id: "r1", fit_score: 10 }),
      job({ id: "fitOnly", run_id: "r0", fit_score: 90 }),
    ];

    const out = applyFilters(jobs, { ...NO_FILTERS, newOnly: true, minFit: 60 }, "r1");

    expect(out.map((j) => j.id)).toEqual(["both"]);
  });
});
