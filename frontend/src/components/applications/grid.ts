// One grid template shared by the table header and every row, so the columns
// stay aligned. Defined once here to avoid the header and rows drifting apart.
// Columns: Organization | Role | Type | Status | Priority | Deadline | Actions.
// The trailing actions column holds the open-posting link and the detail chevron.
export const ROW_GRID =
  "grid grid-cols-[minmax(180px,1.7fr)_minmax(130px,1.2fr)_92px_minmax(130px,160px)_116px_132px_64px] items-center gap-x-4";
