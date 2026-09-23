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

  it("filters by place", () => {
    const jobs = [
      job({ id: "fl", location: "Orlando, FL" }),
      job({ id: "wa", location: "Seattle, WA" }),
    ];

    expect(applyFilters(jobs, { ...NO_FILTERS, place: "fl" }, null).map((j) => j.id)).toEqual(["fl"]);
  });

  it("matches inside a summarised multi-city location", () => {
    // Locations read "Seattle, WA, Austin, TX +28 more" once a posting is open
    // in more places than fit the column.
    const jobs = [job({ id: "a", location: "Seattle, WA, Austin, TX +28 more" })];

    expect(applyFilters(jobs, { ...NO_FILTERS, place: "austin" }, null)).toHaveLength(1);
  });

  it("keeps a posting with no location recorded", () => {
    // Common, and not the same as remote. Dropping it would hide jobs for a
    // reason the data does not support.
    const jobs = [job({ id: "unknown", location: null })];

    expect(applyFilters(jobs, { ...NO_FILTERS, place: "fl" }, null)).toHaveLength(1);
  });

  it("keeps place separate from the company search", () => {
    // Combining them would make both worse: "rivian" should not match a job in
    // Riviera Beach.
    const jobs = [job({ id: "a", organization: "Rivian", location: "Irvine, CA" })];

    expect(applyFilters(jobs, { ...NO_FILTERS, query: "rivian" }, null)).toHaveLength(1);
    expect(applyFilters(jobs, { ...NO_FILTERS, place: "rivian" }, null)).toHaveLength(0);
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
