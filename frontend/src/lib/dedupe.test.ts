import { describe, expect, it } from "vitest";
import type { Application } from "./types";
import {
  findSimilarPosting,
  findUrlMatch,
  normalizeOrganization,
  normalizeUrl,
} from "./dedupe";

// These are the functions that decide whether you get warned before spending a
// paid parse call, so both directions matter: a missed warning costs a
// duplicate row, and a false warning trains you to dismiss the thing unread.

describe("normalizeUrl", () => {
  it("treats the same posting shared two ways as one link", () => {
    expect(normalizeUrl("https://www.Example.com/jobs/42?utm_source=linkedin")).toBe(
      normalizeUrl("http://example.com/jobs/42/"),
    );
  });

  it("keeps the job-board job id, which identifies WHICH posting it is", () => {
    // The tempting shortcut is to drop every query param. That would collapse
    // every Greenhouse posting at a company into one link and warn constantly.
    expect(normalizeUrl("https://boards.greenhouse.io/acme?gh_jid=111")).not.toBe(
      normalizeUrl("https://boards.greenhouse.io/acme?gh_jid=222"),
    );
  });

  it("strips the job-board SOURCE param, which only says how you arrived", () => {
    expect(
      normalizeUrl("https://boards.greenhouse.io/acme?gh_jid=111&gh_src=abc"),
    ).toBe(normalizeUrl("https://boards.greenhouse.io/acme?gh_jid=111&gh_src=zzz"));
  });

  it("ignores param order", () => {
    expect(normalizeUrl("https://x.com/j?b=2&a=1")).toBe(
      normalizeUrl("https://x.com/j?a=1&b=2"),
    );
  });

  it("accepts a URL typed without a scheme", () => {
    expect(normalizeUrl("careers.acme.com/job/7")).toBe("careers.acme.com/job/7");
  });

  it("drops the hash", () => {
    expect(normalizeUrl("https://x.com/j#apply")).toBe("x.com/j");
  });

  it("returns null for empty input", () => {
    expect(normalizeUrl("   ")).toBeNull();
  });

  it("does not throw on something that is not a URL", () => {
    expect(typeof normalizeUrl("not a url at all")).toBe("string");
  });
});

describe("normalizeOrganization", () => {
  it("collapses legal suffixes", () => {
    expect(normalizeOrganization("Google, LLC")).toBe(normalizeOrganization("Google"));
  });

  it("drops a leading article", () => {
    expect(normalizeOrganization("The Walt Disney Company")).toBe("walt disney");
  });

  it("keeps genuinely different employers apart", () => {
    expect(normalizeOrganization("Stripe")).not.toBe(normalizeOrganization("Square"));
  });
});

function app(organization: string, role: string, url = "https://a.com/1") {
  return {
    id: organization + role,
    organization,
    role_or_program: role,
    posting_url: url,
  } as Application;
}

describe("findSimilarPosting", () => {
  const list = [
    app("Google LLC", "Software Engineer Intern, Summer 2027"),
    app("Stripe", "Backend Engineer Intern"),
  ];

  it("catches the same job titled differently on another board", () => {
    // The case the feature exists for, and the one that regressed during the
    // build: without stemming, "Engineer" and "Engineering" share no tokens.
    expect(
      findSimilarPosting(list, "Google", "Software Engineering Internship 2027"),
    ).not.toBeNull();
  });

  it("does not warn on a different team at the same company", () => {
    expect(findSimilarPosting(list, "Google", "Hardware Engineer Intern")).toBeNull();
  });

  it("does not warn across companies", () => {
    expect(findSimilarPosting(list, "Meta", "Software Engineer Intern")).toBeNull();
  });
});

describe("findUrlMatch", () => {
  it("finds a row whose link differs only by tracking noise", () => {
    const list = [app("Acme", "Intern", "https://a.com/1")];
    expect(findUrlMatch(list, "http://www.a.com/1/?utm_campaign=x")).not.toBeNull();
  });

  it("finds nothing for an unrelated link", () => {
    const list = [app("Acme", "Intern", "https://a.com/1")];
    expect(findUrlMatch(list, "https://b.com/9")).toBeNull();
  });
});
