import { useState } from "react";
import type {
  Application,
  FitReport,
  RequirementKind,
  RequirementVerdict,
} from "../../lib/types";
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
  unstated: "Your call",
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
  const preferred = application.jd_parsed?.preferred_qualifications ?? [];
  const hasRequirements = requirements.length + preferred.length > 0;

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
  type Row = {
    requirement: string;
    verdict: RequirementVerdict | null;
    evidence: string | null;
    kind: RequirementKind;
  };
  const rows: Row[] = report
    ? report.matches
    : [
        ...requirements.map((requirement) => ({
          requirement,
          verdict: null,
          evidence: null,
          kind: "required" as const,
        })),
        ...preferred.map((requirement) => ({
          requirement,
          verdict: null,
          evidence: null,
          kind: "preferred" as const,
        })),
      ];

  const requiredRows = rows.filter((r) => r.kind === "required");
  const preferredRows = rows.filter((r) => r.kind === "preferred");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {report ? (
          <div className="flex flex-col gap-1">
            <div className="flex items-baseline gap-2.5">
            {/* Requirements the resume cannot answer are out of the
                denominator. Counting them as failures would report a gap you
                have not actually got. */}
            <span className="text-2xl font-semibold tabular-nums text-ink">
              {report.met_count} of {report.total - report.unstated_count}
            </span>
            <span className="text-[13px] text-ink-soft">
              required met
              {report.partial_count > 0 && `, ${report.partial_count} partial`}
              {report.unstated_count > 0 &&
                `, ${report.unstated_count} for you to confirm`}
            </span>
            </div>
            {report.preferred_total > 0 && (
              // A second line, never folded into the headline: nearly every
              // applicant clears the hard bar, so this is the half that
              // actually separates candidates, but missing a preference is not
              // the same kind of fact as missing a requirement.
              <span className="text-[12.5px] text-ink-muted">
                {report.preferred_met_count} of {report.preferred_total} preferred
                {report.preferred_partial_count > 0 &&
                  `, ${report.preferred_partial_count} partial`}
              </span>
            )}
          </div>
        ) : (
          <span className="text-[12.5px] text-ink-soft">
            {requirements.length} required
            {preferred.length > 0 && ` and ${preferred.length} preferred`}, not
            checked yet.
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

      {/* Listed here whether or not they have been checked, so this section is
          their single home. Checking decorates the same list with a verdict and
          the evidence behind it, rather than printing a second copy further
          down the page. */}
      <RequirementList rows={requiredRows} />
      {preferredRows.length > 0 && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
            Preferred
            <span className="h-px flex-1 bg-line" />
          </div>
          <p className="-mt-1 text-[11.5px] text-ink-muted">
            Not required. This is usually what separates candidates, and the best
            guide to what to emphasize when you tailor.
          </p>
          <RequirementList rows={preferredRows} />
        </div>
      )}

      {report && (
        <p className="text-[11px] text-ink-muted">
          Checked {fmtWhen(report.computed_at)} against your master resume.
          Editing your master can change this.
        </p>
      )}
    </div>
  );
}

function RequirementList({
  rows,
}: {
  rows: {
    requirement: string;
    verdict: RequirementVerdict | null;
    evidence: string | null;
  }[];
}) {
  if (rows.length === 0) return null;
  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => (
        <div
          key={i}
          className="flex items-start gap-3 rounded-frame border border-line bg-surface px-3.5 py-2.5"
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
  );
}

// Neutral greys throughout. docs/design.md reserves the accent for the primary
// action, selection, focus, and an offer — a requirement verdict is not on that
// list, and colour-coding these would put a traffic light in the middle of the
// calmest part of the page.
//
// But the first attempt at that used two 1.5px dots, bg-ink for met and
// bg-ink-soft for partial, with both labels the same muted grey. At that size
// the two are indistinguishable, so the one row you actually need to see looked
// exactly like the three you don't. The whole job of this report is showing the
// gap at a glance.
//
// The fix is CONTRAST, not colour, and it runs the emphasis the other way
// round: a met requirement is settled, so it recedes; partial and missing are
// the ones you act on, so they get the brighter label and a ring that reads at
// small size. Nothing here is on the accent's reserved list.
function VerdictChip({ verdict }: { verdict: RequirementVerdict }) {
  const settled = verdict === "met";
  const dot =
    verdict === "met"
      ? "bg-ink-muted"
      : verdict === "partial"
        ? "border-2 border-ink bg-transparent"
        : verdict === "missing"
          ? "border border-ink"
          : // unstated and unknown: nothing was decided, so nothing is filled in
            "border border-dashed border-ink-muted";

  return (
    <span
      className={`mt-px inline-flex w-[104px] shrink-0 items-center gap-1.5 text-[11.5px] font-medium ${
        settled ? "text-ink-muted" : "text-ink"
      }`}
    >
      <span className={`size-2 shrink-0 rounded-full ${dot}`} />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}
