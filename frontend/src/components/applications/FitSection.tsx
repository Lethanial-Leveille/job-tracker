import { useState } from "react";
import type { Application, FitReport, RequirementVerdict } from "../../lib/types";
import { computeFit } from "../../lib/api";

// How well your master resume answers this posting's stated requirements.
//
// What this is NOT: a probability of getting the job. That number would need an
// outcome history the app does not have, and a made-up percentage reads as
// information while carrying none. This compares two documents already in hand
// and shows its work, so every line is checkable.
//
// It is deliberately blunt. A generous "met" is worthless; an honest "missing"
// tells you what to go fix.

interface Props {
  application: Application;
  // Bubble the freshly computed report up so the page can hold it without a
  // refetch of the whole list.
  onComputed: (report: FitReport) => void;
  report: FitReport | null;
}

const VERDICT_LABEL: Record<RequirementVerdict, string> = {
  met: "Met",
  partial: "Partial",
  missing: "Missing",
  unknown: "Not assessed",
};

function fmtWhen(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function FitSection({ application, onComputed, report }: Props) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const requirements = application.jd_parsed?.key_requirements ?? [];
  const hasRequirements = requirements.length > 0;

  // The report is a function of this posting AND your master resume, and the
  // master changes as you edit it. Rather than guess at staleness, show when it
  // was computed and let Recheck be one click away.
  async function run() {
    setRunning(true);
    setError(null);
    try {
      onComputed(await computeFit(application.id));
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not check the requirements",
      );
    } finally {
      setRunning(false);
    }
  }

  if (!hasRequirements) {
    return (
      <p className="text-[12.5px] text-ink-muted">
        This row has no extracted requirements, so there is nothing to check
        against. Rows added by hand skip the parser; adding one through the paste
        flow captures them.
      </p>
    );
  }

  // One shape for both states: unchecked rows carry no verdict and no evidence.
  const rows: {
    requirement: string;
    verdict: RequirementVerdict | null;
    evidence: string | null;
  }[] = report
    ? report.matches
    : requirements.map((requirement) => ({
        requirement,
        verdict: null,
        evidence: null,
      }));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {report ? (
          <div className="flex items-baseline gap-2.5">
            <span className="text-2xl font-semibold tabular-nums text-ink">
              {report.met_count} of {report.total}
            </span>
            <span className="text-[13px] text-ink-soft">
              requirements met
              {report.partial_count > 0 && `, ${report.partial_count} partial`}
            </span>
          </div>
        ) : (
          <span className="text-[12.5px] text-ink-soft">
            {requirements.length} requirements on file, not checked yet.
          </span>
        )}

        <button
          type="button"
          onClick={run}
          disabled={running}
          className="shrink-0 rounded-interactive border border-line bg-surface px-4 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-50"
        >
          {running ? "Checking…" : report ? "Recheck" : "Check requirements"}
        </button>
      </div>

      {error && (
        <p className="rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink">
          {error}
        </p>
      )}

      {/* The requirements are listed here whether or not they have been
          checked, so this section is their single home. Checking decorates the
          same list with a verdict and the evidence behind it, rather than
          printing a second copy of it further down the page. */}
      <div className="flex flex-col gap-2">
        {rows.map((row, i) => (
          <div
            key={i}
            className="flex items-start gap-3 rounded-frame border border-line bg-surface px-3.5 py-3"
          >
            {row.verdict && <VerdictChip verdict={row.verdict} />}
            <div className="min-w-0 flex-1">
              <p className="text-[13px] leading-snug text-ink">{row.requirement}</p>
              {row.evidence && (
                <p className="mt-1 text-[12px] leading-relaxed text-ink-soft">
                  {row.evidence}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {report && (
        <p className="text-[11px] text-ink-muted">
          Checked {fmtWhen(report.computed_at)} against your master resume.
          Editing your master can change this.
        </p>
      )}
    </div>
  );
}

// Neutral greys throughout. docs/design.md reserves the accent for the primary
// action, selection, focus, and an offer — a requirement verdict is not on that
// list, and colour-coding these would put a traffic light in the middle of the
// calmest part of the page. Weight and fill carry the distinction instead.
function VerdictChip({ verdict }: { verdict: RequirementVerdict }) {
  const dot =
    verdict === "met"
      ? "bg-ink"
      : verdict === "partial"
        ? "bg-ink-soft"
        : verdict === "missing"
          ? "border border-ink-muted"
          : "border border-dashed border-ink-muted";

  return (
    <span className="mt-px inline-flex w-[104px] shrink-0 items-center gap-1.5 text-[11.5px] font-medium text-ink-soft">
      <span className={`size-1.5 shrink-0 rounded-full ${dot}`} />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}
