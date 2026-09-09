import { useMemo } from "react";
import type { Application } from "../../lib/types";
import { formatDeadline } from "../../lib/format";
import { isClosed, isPreSubmit } from "./statuses";

// The four numbers worth a permanent place on the screen.
//
// Deliberately four, not a dashboard. Most beginner stat rows are forty charts
// nobody reads; the test each of these passes is "would seeing this change what
// I do this morning". Counts, not rates — a percentage of 64 rows is a number
// pretending to be a trend.
//
// "Closing ≤7d" counts UNAPPLIED rows only. A deadline you have already met is
// not closing, and counting it here would inflate the one number meant to make
// you act.

const IN_PROCESS = ["assessment", "phone_screen", "technical_interview", "offer"];

interface Bucket {
  discovered: number;
  applied: number;
  offer: number;
  closed: number;
}

function summarize(applications: Application[]) {
  let applied = 0;
  let inProcess = 0;
  let closingSoon = 0;
  const bar: Bucket = { discovered: 0, applied: 0, offer: 0, closed: 0 };

  for (const app of applications) {
    const pre = isPreSubmit(app.status);
    const closed = isClosed(app.status);
    if (!pre && !closed) applied += 1;
    if (IN_PROCESS.includes(app.status)) inProcess += 1;
    if (pre) {
      const days = formatDeadline(app.deadline)?.days;
      if (days !== undefined && days <= 7) closingSoon += 1;
    }

    if (closed) bar.closed += 1;
    else if (app.status === "offer" || app.status === "accepted") bar.offer += 1;
    else if (pre) bar.discovered += 1;
    else bar.applied += 1;
  }

  return { tracked: applications.length, applied, inProcess, closingSoon, bar };
}

function Stat({ label, value, sub }: { label: string; value: number; sub?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-ink-label">
        {label}
      </span>
      <span className="flex items-baseline gap-1.5">
        <span className="text-[16px] font-medium tabular-nums text-ink">{value}</span>
        {sub && <span className="text-[11px] tabular-nums text-ink-spent">{sub}</span>}
      </span>
    </div>
  );
}

export function StatsStrip({ applications }: { applications: Application[] }) {
  const s = useMemo(() => summarize(applications), [applications]);
  if (s.tracked === 0) return null;

  const pct = (n: number) => (s.tracked === 0 ? 0 : (n / s.tracked) * 100);
  const segments = [
    { key: "discovered", width: pct(s.bar.discovered), className: "bg-ink-spent" },
    { key: "applied", width: pct(s.bar.applied), className: "bg-ink-3" },
    // The only purple in the strip, and only when an offer actually exists.
    { key: "offer", width: pct(s.bar.offer), className: "bg-accent-edge shadow-offer-dot" },
    { key: "closed", width: pct(s.bar.closed), className: "bg-line-ctrl" },
  ].filter((seg) => seg.width > 0);

  return (
    <div className="flex flex-wrap items-end justify-between gap-6 rounded-frame border border-line-frame bg-surface-alt px-5 py-3.5">
      <div className="flex flex-wrap items-end gap-x-9 gap-y-3">
        <Stat label="Tracked" value={s.tracked} />
        <Stat
          label="Applied"
          value={s.applied}
          sub={`${Math.round(pct(s.applied))}%`}
        />
        <Stat label="In process" value={s.inProcess} />
        <Stat label="Closing ≤7d" value={s.closingSoon} sub="unapplied" />
      </div>

      <div className="flex w-full max-w-[272px] flex-col gap-1.5">
        <div className="flex h-[5px] gap-px overflow-hidden rounded-full">
          {segments.map((seg) => (
            <div
              key={seg.key}
              style={{ width: `${seg.width}%` }}
              className={`h-full ${seg.className}`}
            />
          ))}
        </div>
        <div className="flex flex-wrap gap-x-3 text-[10px] text-ink-label">
          <span>Saved {s.bar.discovered}</span>
          <span>Applied {s.bar.applied}</span>
          {s.bar.offer > 0 && <span className="text-accent-text">Offer {s.bar.offer}</span>}
          <span>Closed {s.bar.closed}</span>
        </div>
      </div>
    </div>
  );
}
