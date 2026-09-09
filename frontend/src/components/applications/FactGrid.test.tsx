import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Application, ApplicationStatus } from "../../lib/types";
import { FactGrid } from "./FactGrid";

function app(over: Partial<Application> = {}): Application {
  return {
    id: "a",
    organization: "Stripe",
    role_or_program: "SWE Intern",
    status: "discovered" as ApplicationStatus,
    deadline: null,
    applied_at: null,
    role_family: null,
    jd_parsed: null,
    jd_text: null,
    ...over,
  } as unknown as Application;
}
const inDays = (n: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

describe("FactGrid", () => {
  it("keeps the deadline on the record and marks it spent once applied", () => {
    // The LIST retires the deadline because it is not actionable. The record
    // should still hold it — this is the page the record lives on.
    render(
      <FactGrid
        application={app({
          status: "applied" as ApplicationStatus,
          deadline: inDays(-5),
          applied_at: new Date(Date.now() - 6 * 86_400_000).toISOString(),
        })}
      />,
    );
    expect(screen.getByText(/· spent$/)).toBeDefined();
  });

  it("shows the live deadline while the row is still open", () => {
    render(<FactGrid application={app({ deadline: inDays(3) })} />);
    expect(screen.getByText(/in 3 days/)).toBeDefined();
  });

  it("adds sent and quiet to the status once applied", () => {
    render(
      <FactGrid
        application={app({
          status: "applied" as ApplicationStatus,
          applied_at: new Date(Date.now() - 9 * 86_400_000).toISOString(),
        })}
      />,
    );
    expect(screen.getByText(/quiet 9d/)).toBeDefined();
  });

  it("says a field is not stated rather than rendering an empty cell", () => {
    render(<FactGrid application={app()} />);
    expect(screen.getAllByText("Not stated").length).toBeGreaterThan(0);
    expect(screen.getByText("Not set")).toBeDefined();
  });

  it("reports where the grad date suggestion came from", () => {
    render(
      <FactGrid
        application={app({ jd_text: "Open to rising sophomores." } as Partial<Application>)}
      />,
    );
    expect(screen.getByText(/May 2029 · from posting/)).toBeDefined();
  });
});
