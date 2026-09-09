// One column template shared by the table header and every row, so the columns
// stay aligned. Defined once here to avoid the header and rows drifting apart.
// Columns: Organization | Role | Status | Deadline | Actions.
// The trailing actions column holds the open-posting link and the detail chevron.
// Type and Priority were removed: the tracker is jobs-only (so Type read "Job"
// on every row) and priority is tracked in Lee's head, not here.
//
// Responsive: at md+ it's the aligned grid. On phones the fixed column widths
// can't fit, so a row stacks into a mini-card (flex-col) and the header labels
// hide — each stacked value (a bold org, a status pill, a date) reads on its own.
// Tightened for density (v3). The minmax FLOORS came down rather than adding a
// scroll container: any `overflow-x` on an ancestor captures `position: sticky`
// and parks the column header mid-list, so width is fixed by trimming, never by
// scrolling. Minimum is ~596px of table beside a 210px sidebar, which fits any
// laptop without one.
const GRID_COLS =
  "md:grid-cols-[minmax(120px,2fr)_minmax(100px,1.4fr)_minmax(96px,140px)_128px_46px]";

export const ROW_GRID = `flex flex-col gap-1.5 md:grid ${GRID_COLS} md:items-center md:gap-x-4`;
export const HEADER_GRID = `hidden md:grid ${GRID_COLS} md:items-center md:gap-x-4`;
