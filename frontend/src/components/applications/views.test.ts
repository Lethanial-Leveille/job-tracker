import { describe, expect, it } from "vitest";
import type { Application, ApplicationStatus } from "../../lib/types";
import { SAVED_VIEWS, findView } from "./views";

function app(over: Partial<Application> = {}): Application {
  return {
    id: "a",
    status: "discovered" as ApplicationStatus,
    deadline: null,
    applied_at: null,
    ...over,
  } as unknown as Application;
}
const inDays = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const agoIso = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
const view = (k: string) => SAVED_VIEWS.find((v) => v.key === k)!;

describe("Closing in 4 days", () => {
  it("only counts rows you have not applied to", () => {
    expect(view("closing").matches(app({ deadline: inDays(2) }))).toBe(true);
    expect(
      view("closing").matches(
        app({ deadline: inDays(2), status: "applied" as ApplicationStatus }),
      ),
    ).toBe(false);
  });

  it("excludes a row with no deadline rather than treating it as urgent", () => {
    expect(view("closing").matches(app({ deadline: null }))).toBe(false);
  });
});

describe("Quiet 12+ days", () => {
  it("needs an applied date to count from", () => {
    // Status says applied but nothing recorded it: unknown, not quiet.
    expect(
      view("quiet").matches(app({ status: "applied" as ApplicationStatus, applied_at: null })),
    ).toBe(false);
  });

  it("excludes closed rows however long they have been silent", () => {
    expect(
      view("quiet").matches(
        app({ status: "rejected" as ApplicationStatus, applied_at: agoIso(90) }),
      ),
    ).toBe(false);
  });

  it("matches an applied row past the threshold", () => {
    expect(
      view("quiet").matches(
        app({ status: "applied" as ApplicationStatus, applied_at: agoIso(20) }),
      ),
    ).toBe(true);
  });
});

describe("findView", () => {
  it("returns null for an unknown or absent key rather than throwing", () => {
    expect(findView(null)).toBeNull();
    expect(findView("nonsense")).toBeNull();
  });
});
