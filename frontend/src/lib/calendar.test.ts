// The grid is the part of the picker most likely to be quietly wrong: an off by
// one here puts every date in the wrong column, and it only shows in some
// months. So the month shapes that differ are each pinned.

import { describe, expect, it } from "vitest";
import { addDays, fromIso, monthGrid, toIso } from "./calendar";

describe("monthGrid", () => {
  it("starts on the Sunday before a month that starts midweek", () => {
    // September 1, 2026 is a Tuesday.
    const grid = monthGrid(2026, 8);
    expect(grid).toHaveLength(42);
    expect(grid[0]).toBe("2026-08-30");
    expect(grid[2]).toBe("2026-09-01");
    expect(grid[41]).toBe("2026-10-10");
  });

  it("starts on the 1st when the month starts on a Sunday", () => {
    // February 1, 2026 is a Sunday.
    expect(monthGrid(2026, 1)[0]).toBe("2026-02-01");
  });

  it("crosses into the next year", () => {
    const grid = monthGrid(2026, 11);
    expect(grid[0]).toBe("2026-11-29");
    expect(grid[41]).toBe("2027-01-09");
  });

  it("puts every day in the right weekday column", () => {
    const grid = monthGrid(2026, 8);
    grid.forEach((iso, i) => expect(fromIso(iso).getDay()).toBe(i % 7));
  });
});

describe("iso helpers", () => {
  it("round trips without drifting a day", () => {
    // The UTC parsing trap would turn this into the 29th west of UTC.
    expect(toIso(fromIso("2026-09-30"))).toBe("2026-09-30");
  });

  it("rolls days over month and year ends", () => {
    expect(addDays("2026-09-30", 1)).toBe("2026-10-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});
