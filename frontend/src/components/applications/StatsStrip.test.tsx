import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Application, ApplicationStatus } from "../../lib/types";
import { StatsStrip } from "./StatsStrip";

function app(over: Partial<Application> = {}): Application {
  return {
    id: Math.random().toString(36).slice(2),
    status: "discovered" as ApplicationStatus,
    deadline: null,
    // Default to the employer's own date, so a test that only cares about
    // status does not have to think about provenance. The tests that DO care
    // override it.
    deadline_source: "posting" as const,
    applied_at: null,
    ...over,
  } as unknown as Application;
}
const inDays = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

describe("StatsStrip", () => {
  it("renders nothing at all when there is nothing tracked", () => {
    // An empty strip of zeroes is worse than no strip: it takes 58px to say
    // the same thing the empty table below already says.
    const { container } = render(<StatsStrip applications={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("counts only UNAPPLIED rows as closing soon", () => {
    // The number exists to make you act. A deadline you have already met is not
    // closing, and counting it would inflate the one actionable figure.
    render(
      <StatsStrip
        applications={[
          app({ deadline: inDays(3) }),
          app({ deadline: inDays(3), status: "applied" as ApplicationStatus }),
        ]}
      />,
    );
    const label = screen.getByText("Closing ≤7d").parentElement!;
    expect(label.textContent).toContain("1");
  });

  it("does not count a self-imposed date as closing", () => {
    // A date I set so the row would stay visible is a reminder, not a closing
    // date. Nothing is enforcing it, so counting it inflates the one figure
    // meant to make me act, and a counter that cries wolf gets ignored.
    render(
      <StatsStrip
        applications={[
          app({ deadline: inDays(2), deadline_source: "self" }),
          app({ deadline: inDays(2), deadline_source: null }),
        ]}
      />,
    );
    const label = screen.getByText("Closing ≤7d").parentElement!;
    expect(label.textContent).toContain("0");
  });

  it("excludes closed rows from the applied count", () => {
    render(
      <StatsStrip
        applications={[
          app({ status: "applied" as ApplicationStatus }),
          app({ status: "rejected" as ApplicationStatus }),
        ]}
      />,
    );
    const applied = screen.getByText("Applied", { selector: "span" }).parentElement!;
    expect(applied.textContent).toContain("1");
  });

  it("shows no offer legend when there is no offer", () => {
    // The only purple in the strip appears only when it means something.
    render(<StatsStrip applications={[app({ status: "applied" as ApplicationStatus })]} />);
    expect(screen.queryByText(/^Offer /)).toBeNull();
  });
});
