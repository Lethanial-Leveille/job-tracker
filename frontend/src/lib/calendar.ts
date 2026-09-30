// Date math for the DatePicker, kept apart from the component so it can be
// tested without rendering anything.
//
// Every date here is an ISO day string ("2026-09-30"), the same shape the API
// sends and stores. Two traps shape the helpers below, and both shift a day in
// any timezone west of UTC (Florida included):
//
//   1. new Date("2026-09-30") is read as midnight UTC, which is the evening of
//      the 29th locally. So strings are parsed from their parts instead.
//   2. toISOString() converts back to UTC, with the same shift in reverse. So
//      strings are built from local getters instead.

// Months are 0 based throughout (January is 0), matching JavaScript's Date, so
// nothing here has to remember to add or subtract one.

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// Local Date -> "YYYY-MM-DD".
export function toIso(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// "YYYY-MM-DD" -> local Date at midnight.
export function fromIso(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function todayIso(): string {
  return toIso(new Date());
}

// Shift a day by n days. Date handles the month and year rollover: day 32 of
// September is October 2nd.
export function addDays(iso: string, n: number): string {
  const d = fromIso(iso);
  return toIso(new Date(d.getFullYear(), d.getMonth(), d.getDate() + n));
}

// The 42 days a month view shows: 6 weeks of 7, starting on the Sunday on or
// before the 1st. Always 6 rows, even for a month that fits in 5, so the
// popover keeps one height while you page through months.
export function monthGrid(year: number, month: number): string[] {
  const first = new Date(year, month, 1);
  // getDay() is 0 for Sunday, so this steps back to that week's Sunday. A day
  // of 0 or less rolls back into the previous month.
  const start = 1 - first.getDay();
  return Array.from({ length: 42 }, (_, i) => toIso(new Date(year, month, start + i)));
}

// "September 2026", for the header.
export function monthLabel(year: number, month: number): string {
  return new Date(year, month, 1).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}
