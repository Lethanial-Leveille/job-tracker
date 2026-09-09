// The status column's whole job is to make one row stand out from forty that
// look alike, so what is pinned here is the DIFFERENCE between tiers, not the
// exact colours.

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import type { ApplicationStatus } from "../../lib/types";
import { StatusBadge } from "./StatusBadge";

function dotClass(status: ApplicationStatus): string {
  const { container } = render(<StatusBadge status={status} />);
  return container.querySelector("span > span")?.className ?? "";
}

describe("StatusBadge", () => {
  it("gives the offer the only glowing dot", () => {
    // design.md spends the single accent on one "win" state. One glowing dot in
    // 64 rows is the point; a second one anywhere would break the budget.
    expect(dotClass("offer")).toContain("shadow-offer-dot");
  });

  it("does not glow for anything else, including a late-stage interview", () => {
    for (const s of ["applied", "technical_interview", "onsite", "rejected"] as ApplicationStatus[]) {
      expect(dotClass(s)).not.toContain("shadow-offer-dot");
    }
  });

  it("hollows out the dot on closed rows", () => {
    expect(dotClass("rejected")).toContain("bg-transparent");
    expect(dotClass("ghosted")).toContain("bg-transparent");
  });

  it("renders no pill — no background, border or rounded chrome on the label", () => {
    // The regression this guards: reintroducing a filled badge, which is what
    // made 41 consecutive rows unscannable.
    const { container } = render(<StatusBadge status="applied" />);
    const outer = container.firstElementChild as HTMLElement;
    expect(outer.className).not.toMatch(/rounded-full|border|bg-surface/);
  });

  it("still shows the human label, not the raw enum value", () => {
    const { container } = render(<StatusBadge status="discovered" />);
    expect(container.textContent).toBe("Saved");
  });
});
