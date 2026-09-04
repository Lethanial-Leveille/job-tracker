import { describe, expect, it } from "vitest";
import type { Application } from "./types";
import { gradDateHint } from "./gradHint";

// Both directions of this hint cost something real: suggesting the earlier date
// for a sophomore-only program argues for a resume that gets filtered out, and
// suggesting the later one for a junior+ role does the same in reverse. So the
// silent case (null) matters as much as the two verdicts.

function app(over: Partial<Application>): Application {
  return { jd_parsed: null, jd_text: null, ...over } as Application;
}

describe("gradDateHint", () => {
  it("suggests the later date when the posting targets underclassmen", () => {
    const hint = gradDateHint(app({ jd_text: "Open to first year and second year students." }));
    expect(hint?.suggest).toBe("alternate");
  });

  it("suggests the earlier date when the posting wants a rising junior", () => {
    const hint = gradDateHint(
      app({ jd_parsed: { key_requirements: ["Must be a rising junior or senior"] } }),
    );
    expect(hint?.suggest).toBe("primary");
  });

  it("says nothing when the posting is silent about eligibility", () => {
    const hint = gradDateHint(app({ jd_text: "Build backend services in Python. Ship fast." }));
    expect(hint).toBeNull();
  });

  it("cites the phrase it matched so the suggestion can be checked", () => {
    const hint = gradDateHint(app({ jd_text: "Candidates must have junior standing by summer." }));
    expect(hint?.evidence).toContain("junior standing");
  });

  it("reads a graduation window and takes the latest year in it", () => {
    const hint = gradDateHint(
      app({ jd_text: "Graduating between December 2028 and June 2029." }),
    );
    expect(hint?.suggest).toBe("alternate");
  });

  it("suggests the earlier date for a graduation window that ends at 2028", () => {
    const hint = gradDateHint(app({ jd_text: "For students graduating in 2027 or 2028." }));
    expect(hint?.suggest).toBe("primary");
  });

  it("ignores a year that has nothing to do with graduating", () => {
    // Postings mention years constantly: program start dates, fiscal years,
    // "founded in 2029" nonsense. Only a graduation context counts.
    const hint = gradDateHint(app({ jd_text: "Our 2029 product roadmap is ambitious." }));
    expect(hint).toBeNull();
  });

  it("lets an explicit class standing beat a graduation year elsewhere", () => {
    const hint = gradDateHint(
      app({
        jd_parsed: { key_requirements: ["Rising junior preferred"] },
        jd_text: "Graduating by 2030.",
      }),
    );
    expect(hint?.suggest).toBe("primary");
  });
});
