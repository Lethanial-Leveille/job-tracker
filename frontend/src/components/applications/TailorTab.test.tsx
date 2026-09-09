// Render tests for the tailor tab.
//
// These exist because two bugs shipped here in one change, and neither could
// have been caught by the pure-logic suites:
//
//   1. The PDF preview was rendered inside the `tailored &&` block. `tailored`
//      is session state, so on any revisit the Preview button on a SAVED
//      version set state that nothing displayed — a silently dead button.
//   2. The preview was a child of the action row's flex container, so it
//      rendered as a thumbnail beside the buttons rather than below them.
//
// Both are "did the right thing appear, in the right place" questions, which is
// exactly what a render test answers and a unit test cannot.

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Application, Resume, ResumeVersion } from "../../lib/types";

// The tab talks to the API on mount (versions) and on click (render/tailor).
// Mocked at the module boundary so no test needs a server.
vi.mock("../../lib/api", () => ({
  listResumeVersions: vi.fn(),
  renderResume: vi.fn(),
  saveResumeVersion: vi.fn(),
  tailorResume: vi.fn(),
}));

import {
  listResumeVersions,
  renderResume,
  saveResumeVersion,
  tailorResume,
} from "../../lib/api";
import { TailorTab } from "./TailorTab";

const RESUME: Resume = {
  career_stage: "student",
  grad_date_variant: "primary",
  contact: { name: "Lee" },
  summary: null,
  education: [],
  skills: [],
  experience: [],
  projects: [],
  activities: [],
} as unknown as Resume;

function application(over: Partial<Application> = {}): Application {
  return {
    id: "app-1",
    organization: "Super.com",
    role_or_program: "Software Engineer Intern",
    posting_url: "https://example.com/job",
    status: "applied",
    priority: "medium",
    type: "job",
    deadline: null,
    notes: null,
    role_family: null,
    jd_parsed: null,
    jd_text: "We are hiring an intern.",
    fit_report: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    ...over,
  } as unknown as Application;
}

function savedVersion(): ResumeVersion {
  return {
    id: "ver-1",
    application_id: "app-1",
    resume: RESUME,
    job_description: "We are hiring an intern.",
    created_at: "2026-09-09T00:00:00Z",
  } as unknown as ResumeVersion;
}

beforeEach(() => {
  vi.mocked(listResumeVersions).mockResolvedValue([]);
  vi.mocked(renderResume).mockResolvedValue({
    blob: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
    filename: "Leveille_Lethanial_Resume_Super.pdf",
  });
  vi.mocked(tailorResume).mockResolvedValue(RESUME);
  // Generating auto-saves the FIRST pass so a draft is never lost, so this is
  // called even when a test never clicks Save. Returning undefined here put an
  // undefined row in the versions list and crashed the render.
  vi.mocked(saveResumeVersion).mockResolvedValue(savedVersion());
});

describe("previewing a saved version", () => {
  it("shows the PDF preview with no draft in session — the regression", async () => {
    // The exact reported case: reopen an application you already applied to.
    // There is no draft, so the Draft section never renders, and a preview
    // living inside it could never appear.
    vi.mocked(listResumeVersions).mockResolvedValue([savedVersion()]);
    const user = userEvent.setup();

    render(<TailorTab application={application()} onStatusChange={vi.fn()} />);

    const previewButton = await screen.findByRole("button", { name: /preview/i });
    await user.click(previewButton);

    expect(await screen.findByTitle("Resume preview")).toBeDefined();
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeDefined();
  });

  it("does not write a file to disk just for looking at it", async () => {
    // Rendering used to build an <a download> and click it, so every look put a
    // PDF in ~/Downloads. Previewing must not touch the anchor path.
    vi.mocked(listResumeVersions).mockResolvedValue([savedVersion()]);
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click");
    const user = userEvent.setup();

    render(<TailorTab application={application()} onStatusChange={vi.fn()} />);
    await user.click(await screen.findByRole("button", { name: /preview/i }));
    await screen.findByTitle("Resume preview");

    expect(clicked).not.toHaveBeenCalled();
    clicked.mockRestore();
  });
});

describe("the graduation-date checkbox", () => {
  // The checkbox lives in the draft action row, so a draft has to exist first.
  async function renderWithDraft(jdText: string) {
    const user = userEvent.setup();
    render(
      <TailorTab application={application({ jd_text: jdText })} onStatusChange={vi.fn()} />,
    );
    await user.click(screen.getByRole("button", { name: /generate tailored resume/i }));
    return screen.findByRole("checkbox", { name: /later grad date/i });
  }

  it("pre-selects the later date when the posting names a class standing", async () => {
    const box = await renderWithDraft("This program is open to rising sophomores only.");
    expect((box as HTMLInputElement).checked).toBe(true);
  });

  it("leaves the checkbox alone when the hint is only inferred from a year", async () => {
    // The year path takes the maximum of a range, so it is a guess and may
    // suggest but never decide.
    const box = await renderWithDraft(
      "Open to candidates graduating between December 2028 and June 2029.",
    );
    expect((box as HTMLInputElement).checked).toBe(false);
  });
});
