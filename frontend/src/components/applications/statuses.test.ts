import { describe, expect, it } from "vitest";
import { ALL_STATUSES, MORE_STATUSES, QUICK_STATUSES, isPreSubmit, menuStatuses } from "./statuses";

describe("status lists", () => {
  it("covers every backend value exactly once between quick and more", () => {
    // If a status went missing from both lists it would become unreachable in
    // the UI, and a row could get stuck on a value nothing can change.
    expect([...QUICK_STATUSES, ...MORE_STATUSES].sort()).toEqual(
      [...ALL_STATUSES].sort(),
    );
  });

  it("has no overlap between the two lists", () => {
    expect(QUICK_STATUSES.filter((s) => MORE_STATUSES.includes(s))).toEqual([]);
  });
});

describe("menuStatuses", () => {
  it("offers just the short list for a common status", () => {
    expect(menuStatuses("applied")).toEqual(QUICK_STATUSES);
  });

  it("prepends a status that is not in the short list", () => {
    // A <select> whose value matches no option renders blank and silently
    // reports the first option instead — so an old "Ghosted" row would appear
    // to be "Discovered" and change itself on first interaction.
    const options = menuStatuses("ghosted");
    expect(options[0]).toBe("ghosted");
    expect(options).toHaveLength(QUICK_STATUSES.length + 1);
  });
});

describe("isPreSubmit", () => {
  it("is true only before an application goes out the door", () => {
    expect(isPreSubmit("discovered")).toBe(true);
    expect(isPreSubmit("ready")).toBe(true);
    expect(isPreSubmit("applied")).toBe(false);
    expect(isPreSubmit("offer")).toBe(false);
  });
});
