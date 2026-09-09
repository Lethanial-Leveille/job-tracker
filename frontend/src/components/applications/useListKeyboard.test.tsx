// The two failure modes that matter for a global key handler: it fires when it
// should not (typing "e" in the search box marking a row applied), and it does
// not fire when it should.

import { describe, expect, it, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Application, ApplicationStatus } from "../../lib/types";
import { useListKeyboard } from "./useListKeyboard";

function app(id: string, over: Partial<Application> = {}): Application {
  return {
    id,
    organization: `Org ${id}`,
    role_or_program: "SWE Intern",
    status: "discovered" as ApplicationStatus,
    deadline: null,
    applied_at: null,
    ...over,
  } as unknown as Application;
}

function Harness({
  applications,
  onOpen = vi.fn(),
  onStatusChange = vi.fn(),
  withInput = false,
}: {
  applications: Application[];
  onOpen?: (id: string) => void;
  onStatusChange?: (id: string, s: ApplicationStatus) => void;
  withInput?: boolean;
}) {
  const kb = useListKeyboard({ applications, onOpen, onStatusChange });
  return (
    <div>
      {withInput && <input aria-label="search" />}
      <span data-testid="selected">{kb.selectedId ?? "none"}</span>
      <span data-testid="undo">{kb.lastChange?.organization ?? "none"}</span>
      <button type="button" onClick={kb.undo}>
        undo
      </button>
    </div>
  );
}

const rows = [app("a"), app("b"), app("c")];

describe("moving", () => {
  it("selects the first row on j from nothing, not the second", async () => {
    const user = userEvent.setup();
    render(<Harness applications={rows} />);
    await user.keyboard("j");
    expect(screen.getByTestId("selected").textContent).toBe("a");
  });

  it("moves down and back up, stopping at the ends", async () => {
    const user = userEvent.setup();
    render(<Harness applications={rows} />);
    await user.keyboard("jjjjj");
    expect(screen.getByTestId("selected").textContent).toBe("c");
    await user.keyboard("kkkkk");
    expect(screen.getByTestId("selected").textContent).toBe("a");
  });
});

describe("acting", () => {
  it("opens the selected row on Enter", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<Harness applications={rows} onOpen={onOpen} />);
    await user.keyboard("j{Enter}");
    expect(onOpen).toHaveBeenCalledWith("a");
  });

  it("marks applied on e and offers an undo", async () => {
    const onStatusChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness applications={rows} onStatusChange={onStatusChange} />);
    await user.keyboard("je");
    expect(onStatusChange).toHaveBeenCalledWith("a", "applied");
    expect(screen.getByTestId("undo").textContent).toBe("Org a");
  });

  it("restores the previous status on undo", async () => {
    const onStatusChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness applications={rows} onStatusChange={onStatusChange} />);
    await user.keyboard("je");
    await user.click(screen.getByRole("button", { name: "undo" }));
    expect(onStatusChange).toHaveBeenLastCalledWith("a", "discovered");
  });

  it("does nothing on e when the row is already applied", async () => {
    const onStatusChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Harness
        applications={[app("a", { status: "applied" as ApplicationStatus })]}
        onStatusChange={onStatusChange}
      />,
    );
    await user.keyboard("je");
    expect(onStatusChange).not.toHaveBeenCalled();
  });
});

describe("staying out of the way", () => {
  it("ignores keys typed into a field", async () => {
    // The bug this prevents: typing "Jane" or "e" in the search box moving the
    // cursor or marking a row applied.
    const onStatusChange = vi.fn();
    const user = userEvent.setup();
    render(<Harness applications={rows} onStatusChange={onStatusChange} withInput />);

    await user.click(screen.getByLabelText("search"));
    await user.keyboard("jek");

    expect(onStatusChange).not.toHaveBeenCalled();
    expect(screen.getByTestId("selected").textContent).toBe("none");
  });
});

describe("selection hygiene", () => {
  it("drops a selection when filtering removes that row", () => {
    const { rerender } = render(<Harness applications={rows} />);
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "j" }));
    });
    expect(screen.getByTestId("selected").textContent).toBe("a");

    rerender(<Harness applications={[app("b"), app("c")]} />);
    expect(screen.getByTestId("selected").textContent).toBe("none");
  });
});
