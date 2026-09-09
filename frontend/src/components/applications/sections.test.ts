import { describe, expect, it } from "vitest";
import type { Application, ApplicationStatus } from "../../lib/types";
import { sectionByUrgency } from "./sections";

function app(over: Partial<Application> = {}): Application {
  return {
    id: Math.random().toString(36).slice(2),
    organization: "Stripe",
    role_or_program: "SWE Intern",
    posting_url: "https://example.com",
    status: "discovered" as ApplicationStatus,
    deadline: null,
    applied_at: null,
    ...over,
  } as unknown as Application;
}

function inDays(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
const agoIso = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

describe("sectionByUrgency", () => {
  it("splits rows by what you can do about them", () => {
    const sections = sectionByUrgency([
      app({ deadline: inDays(2) }),
      app({ deadline: inDays(20) }),
      app({ status: "applied" as ApplicationStatus, applied_at: agoIso(5) }),
      app({ status: "rejected" as ApplicationStatus }),
    ]);

    expect(sections.map((s) => s.key)).toEqual(["closing", "open", "in_flight", "closed"]);
  });

  it("omits empty bands rather than heading nothing", () => {
    const sections = sectionByUrgency([app({ deadline: inDays(2) })]);
    expect(sections.map((s) => s.key)).toEqual(["closing"]);
  });

  it("puts an open row with no deadline in 'open', never in 'closing'", () => {
    // A null deadline is not urgent; it is unknown. Treating it as urgent would
    // put every undated row at the top of the list forever.
    const sections = sectionByUrgency([app({ deadline: null })]);
    expect(sections[0].key).toBe("open");
  });

  it("sorts in-flight by descending silence, not by deadline", () => {
    const sections = sectionByUrgency([
      app({ organization: "Recent", status: "applied" as ApplicationStatus, applied_at: agoIso(2) }),
      app({ organization: "Stale", status: "applied" as ApplicationStatus, applied_at: agoIso(30) }),
    ]);
    expect(sections[0].applications[0].organization).toBe("Stale");
  });

  it("keeps a closed row closed even when its deadline is still ahead", () => {
    const sections = sectionByUrgency([
      app({ status: "rejected" as ApplicationStatus, deadline: inDays(1) }),
    ]);
    expect(sections[0].key).toBe("closed");
  });
});
