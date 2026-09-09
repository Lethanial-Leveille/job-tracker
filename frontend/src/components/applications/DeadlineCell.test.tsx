// The deadline column carries three different meanings depending on where the
// row is, and picking the wrong one is invisible in a screenshot — a "Sent"
// date and a deadline look identical at a glance. So each branch is pinned.

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import type { Application, ApplicationStatus } from "../../lib/types";
import { DeadlineCell } from "./DeadlineCell";

function app(over: Partial<Application> = {}): Application {
  return {
    id: "a1",
    organization: "Stripe",
    role_or_program: "SWE Intern",
    posting_url: "https://example.com",
    status: "discovered" as ApplicationStatus,
    priority: "medium",
    type: "job",
    deadline: null,
    notes: null,
    role_family: null,
    jd_parsed: null,
    jd_text: null,
    fit_report: null,
    applied_at: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  } as unknown as Application;
}

function isoDaysFromNow(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString();
}

describe("still open — the deadline is the point of the row", () => {
  it("shows the date and how long is left", () => {
    render(<DeadlineCell application={app({ deadline: isoDaysFromNow(3) })} />);
    expect(screen.getByText(/in 3 days/)).toBeDefined();
  });

  it("shows an em dash when there is no deadline at all", () => {
    render(<DeadlineCell application={app({ deadline: null })} />);
    expect(screen.getByText("—")).toBeDefined();
  });
});

describe("out the door — count silence, not a deadline", () => {
  it("replaces the deadline with the sent date and a quiet counter", () => {
    render(
      <DeadlineCell
        application={app({
          status: "applied" as ApplicationStatus,
          deadline: isoDaysFromNow(30),
          applied_at: isoDaysAgo(7),
        })}
      />,
    );

    expect(screen.getByText(/^Sent /)).toBeDefined();
    expect(screen.getByText("quiet 7d")).toBeDefined();
    // The deadline must NOT be rendered: it is not actionable any more, and
    // showing it is the noise this whole rule exists to remove.
    expect(screen.queryByText(/in \d+ days/)).toBeNull();
  });

  it("falls back to an em dash when the row was never actually applied", () => {
    // A row imported straight into a later stage has no `applied` event, so
    // there is nothing honest to count from.
    render(
      <DeadlineCell
        application={app({ status: "phone_screen" as ApplicationStatus, applied_at: null })}
      />,
    );
    expect(screen.getByText("—")).toBeDefined();
  });
});

describe("closed — nothing to wait for", () => {
  it("retires the column entirely", () => {
    render(
      <DeadlineCell
        application={app({
          status: "rejected" as ApplicationStatus,
          deadline: isoDaysFromNow(5),
          applied_at: isoDaysAgo(40),
        })}
      />,
    );
    expect(screen.getByText("—")).toBeDefined();
    expect(screen.queryByText(/quiet/)).toBeNull();
  });

  it("keeps missed_deadline closed rather than counting silence", () => {
    // missed_deadline never went out the door, so isSubmitted excludes it, but
    // it IS closed — the two predicates disagree on purpose.
    render(
      <DeadlineCell application={app({ status: "missed_deadline" as ApplicationStatus })} />,
    );
    expect(screen.getByText("—")).toBeDefined();
  });
});
