// One grid template shared by the table header and every row, so the columns
// stay aligned. Defined once here to avoid the header and rows drifting apart.
// Columns: Organization | Role | Status | Deadline | Actions.
// The trailing actions column holds the open-posting link and the detail chevron.
// Type and Priority were removed: the tracker is jobs-only (so Type read "Job"
// on every row) and priority is tracked in Lee's head, not here.
export const ROW_GRID =
  "grid grid-cols-[minmax(220px,2fr)_minmax(170px,1.5fr)_minmax(140px,180px)_140px_64px] items-center gap-x-4";
