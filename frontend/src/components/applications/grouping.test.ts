import { describe, expect, it } from "vitest";
import type { Application } from "../../lib/types";
import { groupByOrganization } from "./grouping";

function app(organization: string, deadline: string | null, id = organization + deadline) {
  return { id, organization, role_or_program: "Intern", deadline } as Application;
}

describe("groupByOrganization", () => {
  it("groups inconsistent spellings of one employer together", () => {
    const groups = groupByOrganization([
      app("Google", "2026-10-01"),
      app("Google LLC", "2026-11-01"),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].applications).toHaveLength(2);
  });

  it("displays the most common spelling, shortest breaking a tie", () => {
    const groups = groupByOrganization([
      app("Google LLC", "2026-10-01", "a"),
      app("Google", "2026-11-01", "b"),
    ]);
    // One each, so the tie goes to the shorter, cleaner human name.
    expect(groups[0].label).toBe("Google");
  });

  it("orders groups by their soonest deadline, so urgency survives grouping", () => {
    const groups = groupByOrganization([
      app("Zeta", "2026-12-01"),
      app("Alpha", "2026-09-01"),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["Alpha", "Zeta"]);
  });

  it("puts groups with no deadline last", () => {
    const groups = groupByOrganization([
      app("Nodate", null),
      app("Dated", "2026-12-01"),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["Dated", "Nodate"]);
  });

  it("keeps every application, losing none to bucketing", () => {
    const input = [
      app("Google", "2026-10-01", "a"),
      app("Google LLC", "2026-11-01", "b"),
      app("Stripe", null, "c"),
    ];
    const total = groupByOrganization(input).flatMap((g) => g.applications).length;
    expect(total).toBe(input.length);
  });
});
