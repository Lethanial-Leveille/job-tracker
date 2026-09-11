import { useState } from "react";
import { Link } from "react-router-dom";
import type {
  Application,
  DiscoveredJob,
  DiscoveryRun,
  Eligibility,
} from "../../lib/types";
import {
  acceptDiscovered,
  dismissDiscovered,
  parseJobDescription,
  parseJobUrl,
} from "../../lib/api";
import { useDiscovered } from "../../lib/useDiscovered";
import { groupDiscoveries } from "./groupDiscoveries";
import {
  applyFilters,
  NO_FILTERS,
  PAGE_SIZE,
  type DiscoveryFilters,
} from "./discoveryFilters";
import { shortDate } from "../../lib/format";

// The discovery inbox: jobs a nightly feed pull found, waiting to be accepted or
// dismissed. Nothing here is in your pipeline yet — accepting files it, and
// dismissing keeps a server-side record so tomorrow's pull cannot offer it again.
//
// The design rule this screen leans on hardest is "drama in the frame, calm in
// the data" (docs/design.md). Every row carries up to three pieces of judgement
// — a role family, an eligibility verdict, a possible-duplicate warning — and it
// would be easy to make each one loud. They are all muted greys except the one
// that should stop you: a graduation mismatch. Purple appears once on the whole
// screen, on the pull button.

interface Props {
  // The pipeline as already loaded by useApplications. Passed in rather than
  // refetched: the duplicate warning needs to name a row, and the list is
  // already in memory upstairs.
  applications: Application[];
  onChanged: () => void;
}

function eligibilityNote(eligibility: Eligibility | null, enriched: string | null) {
  // Four states that look alike if you are careless.
  //
  // A null object with no read timestamp means the posting was never read — a
  // site needing a browser, or a link already gone dead. "unclear" means it WAS
  // read and said nothing about graduation timing, which is true of most
  // postings and deliberately shows NOTHING: a chip appearing on half your
  // inbox that amounts to "go read it yourself" is a chip you stop seeing.
  //
  // Only two states earn a mark, and they are different marks. A mismatch is
  // out of reach. "eligible_early" is within reach on your earlier graduation
  // date, which is a choice to make on purpose rather than by accident.
  if (!eligibility) {
    return enriched
      ? null
      : { tone: "quiet" as const, text: "Posting couldn't be read" };
  }
  const wants = eligibility.wanted_years.join("–");
  // "too_early" is deliberately absent: those rows never reach this screen.
  if (eligibility.verdict === "too_late") {
    return {
      tone: "warn" as const,
      text: `Wants ${wants} — you graduate ${eligibility.your_years.join(" or ")}`,
      detail: eligibility.evidence ?? undefined,
    };
  }
  if (eligibility.verdict === "eligible_early") {
    return {
      tone: "warn" as const,
      text: `Wants ${wants} — only if you use your earlier date`,
      detail: eligibility.evidence ?? undefined,
    };
  }
  if (eligibility.verdict === "eligible") {
    return {
      tone: "ok" as const,
      text: `Graduation year fits (${wants})`,
      detail: eligibility.evidence ?? undefined,
    };
  }
  // Read, and it said nothing that decides anything. Show nothing.
  return null;
}

const TONE = {
  // The only chip meant to stop you. Still grey, not purple: docs/design.md
  // reserves the accent for the primary action and one genuine win state, and a
  // warning that shouted would break "calm in the data" on every row it hit.
  warn: "border-line-strong bg-surface-hover font-medium text-ink",
  ok: "border-line bg-surface text-ink-soft",
  quiet: "border-line bg-surface text-ink-muted",
};

function Chip({ children, tone = "quiet" }: { children: React.ReactNode; tone?: keyof typeof TONE }) {
  return (
    <span className={`inline-flex items-center rounded-interactive border px-2 py-0.5 text-[11px] ${TONE[tone]}`}>
      {children}
    </span>
  );
}

// The headline number, phrased as what it is rather than as a percentage.
// "Matches 4 of 5 requirements" is checkable; "80%" is a score you either
// believe or ignore.
function fitLabel(job: DiscoveredJob): string | null {
  if (job.fit_score === null) return null;
  const report = job.fit_report as
    | { met_count?: number; partial_count?: number; total?: number; unstated_count?: number }
    | null;
  if (!report?.total) return `Strong match`;
  const judged = report.total - (report.unstated_count ?? 0);
  const met = report.met_count ?? 0;
  const partial = report.partial_count ?? 0;
  const extra = partial > 0 ? `, ${partial} partly` : "";
  return `Meets ${met} of ${judged}${extra}`;
}

// Asked for at the moment of accepting, and only when the overnight pass could
// not read the posting. Roughly four in ten ordinary careers sites need a
// browser, and filing one of those as-is gives you a title, a link, and nothing
// to tailor against — a gap you would not notice until you sat down to write
// the resume weeks later.
//
// Two ways in, same as the add screen: the link usually works, and pasting
// always does.
function SupplyPosting({
  onTrack,
  onSkip,
  busy,
}: {
  onTrack: (posting: { jd_text: string; jd_parsed: Record<string, unknown> | null }) => void;
  onSkip: () => void;
  busy: boolean;
}) {
  const [link, setLink] = useState("");
  const [text, setText] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function read() {
    setWorking(true);
    setError(null);
    try {
      if (text.trim() !== "") {
        // Pasted text wins when both are filled: it is already in hand, costs
        // no fetch, and cannot fail.
        const parsed = await parseJobDescription(text);
        onTrack({ jd_text: text, jd_parsed: parsed as unknown as Record<string, unknown> });
        return;
      }
      const result = await parseJobUrl(link);
      onTrack({ jd_text: result.jd_text, jd_parsed: result.parsed as unknown as Record<string, unknown> });
    } catch (err: unknown) {
      // The backend writes fetch failures as a sentence meant to be read here.
      setError(err instanceof Error ? err.message : "Could not read that");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="mt-3 rounded-interactive border border-line bg-base px-4 py-3.5">
      <p className="text-[12.5px] text-ink-soft">
        This posting could not be read overnight. Give it a link or paste the
        description and it will be filled in.
      </p>

      <input
        className="mt-2.5 w-full rounded-interactive border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
        value={link}
        onChange={(e) => setLink(e.target.value)}
        placeholder="Paste the posting link"
      />
      <textarea
        className="mt-2 w-full resize-y rounded-interactive border border-line bg-surface px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="…or paste the description here"
      />

      {error && <p className="mt-2 text-[11.5px] text-ink">{error}</p>}

      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={read}
          disabled={working || busy || (link.trim() === "" && text.trim() === "")}
          className="rounded-interactive border border-accent-line bg-surface-hover px-3 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:shadow-glow disabled:opacity-50"
        >
          {working ? "Reading…" : "Read and track"}
        </button>
        {/* The escape hatch. Some postings genuinely cannot be read and you
            still want the row; making that impossible would be worse. */}
        <button
          type="button"
          onClick={onSkip}
          disabled={working || busy}
          className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft disabled:opacity-50"
        >
          Track without it
        </button>
      </div>
    </div>
  );
}

type Posting = { jd_text: string; jd_parsed: Record<string, unknown> | null };

function Row({
  job,
  others = [],
  applications,
  isNew,
  onAccept,
  onDismiss,
  onAcceptOther,
  onDismissOther,
  busy,
}: {
  job: DiscoveredJob;
  others?: DiscoveredJob[];
  applications: Application[];
  isNew: boolean;
  onAccept: (posting?: Posting) => void;
  onDismiss: () => void;
  onAcceptOther?: (job: DiscoveredJob, posting?: Posting) => void;
  onDismissOther?: (job: DiscoveredJob) => void;
  busy: boolean;
}) {
  const note = eligibilityNote(job.eligibility, job.enriched_at);
  // A row with no posting text is one the overnight pass could not read.
  // Tracking it as-is files a title and a link with nothing to tailor against.
  const unread = job.enriched_at === null || job.eligibility === null;
  const [asking, setAsking] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const maybe = (job.possible_application_ids ?? [])
    .map((id) => applications.find((a) => a.id === id))
    .filter((a): a is Application => a !== undefined);

  return (
    <li className="rounded-frame border border-line bg-surface px-5 py-4 transition-colors hover:border-line-strong">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            {/* The one thing on a row allowed to use the accent, because it is
                the only thing that is genuinely new information rather than a
                property of the job. */}
            {isNew && (
              <span className="rounded-interactive border border-accent-line px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-accent">
                New
              </span>
            )}
            <span className="text-[13px] font-medium text-ink-soft">{job.organization}</span>
            {job.posted_at && (
              <span className="text-[11px] text-ink-muted">Posted {shortDate(job.posted_at)}</span>
            )}
          </div>
          <a
            href={job.posting_url}
            target="_blank"
            rel="noreferrer"
            className="mt-0.5 block truncate text-[15px] text-ink hover:text-accent"
          >
            {job.role_or_program}
          </a>

          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {/* Fit first: it is the reason this row is where it is in the list. */}
            {fitLabel(job) && <Chip tone={job.fit_score! >= 60 ? "ok" : "quiet"}>{fitLabel(job)}</Chip>}
            {job.role_family && <Chip>{job.role_family}</Chip>}
            {/* Only for direct board records. The aggregator is the default, so
                labelling every feed row would be noise; a row read straight off
                the employer's board is the one worth pointing at, because it is
                fresher and its link goes to the posting rather than a list. */}
            {job.source !== "simplify" && <Chip>From their board</Chip>}
            {job.location && <Chip>{job.location}</Chip>}
            {note && <Chip tone={note.tone}>{note.text}</Chip>}
          </div>

          {/* The sentence behind a verdict, always shown when there is one. A
              verdict you cannot check is one you either obey blindly or ignore. */}
          {note?.detail && (
            <p className="mt-2 border-l border-line pl-3 text-[11.5px] leading-relaxed text-ink-muted">
              {note.detail}
            </p>
          )}

          {/* Shown, never hidden: reapplying to a role in a new cycle is real,
              so this warns and lets you decide rather than dropping the row. */}
          {maybe.length > 0 && (
            <p className="mt-2 text-[11.5px] text-ink-soft">
              You may already have this:{" "}
              {maybe.map((a, i) => (
                <span key={a.id}>
                  {i > 0 && ", "}
                  <a href={`/applications/${a.id}`} className="underline hover:text-accent">
                    {a.role_or_program}
                  </a>{" "}
                  <span className="text-ink-muted">({a.status.replace(/_/g, " ")})</span>
                </span>
              ))}
            </p>
          )}
        </div>

        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={onDismiss}
            disabled={busy}
            className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft disabled:opacity-50"
          >
            Dismiss
          </button>
          <button
            type="button"
            onClick={() => (unread ? setAsking(true) : onAccept())}
            disabled={busy || asking}
            className="rounded-interactive border border-line-strong bg-surface-hover px-3 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-accent-line disabled:opacity-50"
          >
            Track it
          </button>
        </div>
      </div>

      {asking && (
        <SupplyPosting
          busy={busy}
          onTrack={(posting) => onAccept(posting)}
          onSkip={() => onAccept()}
        />
      )}

      {/* The folded set: one line, expandable. Everything stays reachable. */}
      {others.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-[11.5px] text-ink-muted transition-colors hover:text-ink-soft"
          >
            {expanded ? "Hide" : "Show"} {others.length} similar posting
            {others.length === 1 ? "" : "s"} at {job.organization}
          </button>
          {expanded && (
            <ul className="mt-2.5 flex flex-col gap-1.5">
              {others.map((other) => (
                <li
                  key={other.id}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-interactive border border-line bg-base px-3 py-2"
                >
                  <a
                    href={other.posting_url}
                    target="_blank"
                    rel="noreferrer"
                    className="min-w-0 flex-1 truncate text-[12.5px] text-ink-soft hover:text-accent"
                  >
                    {other.role_or_program}
                    {other.location && (
                      <span className="text-ink-muted"> · {other.location}</span>
                    )}
                  </a>
                  <div className="flex shrink-0 gap-1.5">
                    <button
                      type="button"
                      onClick={() => onDismissOther?.(other)}
                      className="rounded-interactive border border-line px-2 py-1 text-[11.5px] text-ink-muted hover:text-ink-soft"
                    >
                      Dismiss
                    </button>
                    <button
                      type="button"
                      onClick={() => onAcceptOther?.(other)}
                      className="rounded-interactive border border-line-strong px-2 py-1 text-[11.5px] text-ink hover:border-accent-line"
                    >
                      Track it
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function relative(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function RunBanner({ run }: { run: DiscoveryRun }) {
  if (run.state === "running") {
    const stalled = Date.now() - new Date(run.started_at).getTime() > 20 * 60_000;
    if (stalled) {
      // Says what happened rather than spinning forever. The usual cause is a
      // deploy landing mid-pull, which kills the background task; the server
      // clears those when it next boots.
      return (
        <div className="mt-4 rounded-frame border border-line-strong bg-surface-hover px-4 py-3">
          <p className="text-[12.5px] font-medium text-ink">
            A pull started {relative(run.started_at)} and never reported back.
          </p>
          <p className="mt-1 text-[11.5px] text-ink-muted">
            Usually a deploy landing mid-run. Press Pull now to start a fresh one.
          </p>
        </div>
      );
    }
    return (
      <div className="mt-4 flex items-center gap-3 rounded-frame border border-line bg-surface px-4 py-3">
        <span className="size-3.5 animate-spin rounded-full border-2 border-line-strong border-t-accent motion-reduce:animate-none" />
        <p className="text-[12.5px] text-ink-soft">
          Pulling since {relative(run.started_at)}. Downloading the feed, then
          reading whatever is new. You can leave this page.
        </p>
      </div>
    );
  }
  if (run.state === "failed") {
    // Shown in full rather than summarised. A pull that failed silently is the
    // exact thing the run record exists to prevent.
    return (
      <div className="mt-4 rounded-frame border border-line-strong bg-surface-hover px-4 py-3">
        <p className="text-[12.5px] font-medium text-ink">
          The last pull failed {relative(run.started_at)}.
        </p>
        {run.error && (
          <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">{run.error}</p>
        )}
      </div>
    );
  }
  return (
    <p className="mt-4 text-[12.5px] text-ink-muted">
      Last pull {relative(run.started_at)}: {run.staged} new, {run.enriched} read,{" "}
      {run.duplicates} already seen
      {run.rescored > 0 && `, ${run.rescored} re-judged`}
      {run.ruled_out > 0 && `, ${run.ruled_out} ruled out on graduation year`}.
    </p>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-interactive border px-3 py-1.5 text-[12px] transition-colors ${
        active
          ? "border-accent-line bg-surface-hover text-ink"
          : "border-line text-ink-muted hover:border-line-strong hover:text-ink-soft"
      }`}
    >
      {children}
    </button>
  );
}

export function DiscoveredPage({ applications, onChanged }: Props) {
  const { jobs, loading, error, pulling, run, refetch, pull } = useDiscovered();
  const [busy, setBusy] = useState<string | null>(null);
  const [filters, setFilters] = useState<DiscoveryFilters>(NO_FILTERS);
  const [page, setPage] = useState(0);

  // Narrow, then fold, then page — in that order. Folding after filtering means
  // a group's leader is the best row that SURVIVED the filter, rather than one
  // that was filtered out taking its whole group with it.
  const visible = applyFilters(jobs, filters, run?.id ?? null);
  const groups = groupDiscoveries(visible);
  const pages = Math.max(1, Math.ceil(groups.length / PAGE_SIZE));
  // Clamped rather than reset: changing a filter should not throw you back to
  // the top when the page you were on still exists.
  const current = Math.min(page, pages - 1);
  const shown = groups.slice(current * PAGE_SIZE, (current + 1) * PAGE_SIZE);

  function setFilter(change: Partial<DiscoveryFilters>) {
    setFilters({ ...filters, ...change });
    // A narrower list means page four may no longer exist, and landing on an
    // empty page reads as "the filter found nothing".
    setPage(0);
  }

  async function accept(
    job: DiscoveredJob,
    posting?: { jd_text: string; jd_parsed: Record<string, unknown> | null },
  ) {
    setBusy(job.id);
    try {
      await acceptDiscovered(job.id, posting);
      await refetch();
      // Refresh the pipeline upstairs so the new row is there when you go look.
      onChanged();
      // Deliberately no navigation. Triaging an inbox is a rhythm — read,
      // decide, next — and jumping to the application you just filed breaks it
      // every single time, then leaves you pressing back to return to a list
      // that has moved on. The row disappearing from the list is confirmation
      // enough.
    } finally {
      setBusy(null);
    }
  }

  async function dismiss(job: DiscoveredJob) {
    setBusy(job.id);
    try {
      await dismissDiscovered(job.id);
      await refetch();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto max-w-[880px] px-2 pb-20 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
        <div>
          <h1 className="font-serif text-[28px] font-semibold text-ink">Discovered</h1>
          <p className="mt-1.5 text-[13px] text-ink-soft">
            Internships a nightly pull found. Nothing here is in your pipeline until
            you say so.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/discovered/companies"
            className="rounded-interactive border border-line px-3 py-2 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft"
          >
            Watchlist
          </Link>
          {/* The one primary action on the screen, and so the one place purple
              appears (docs/design.md: purple should feel like it costs
              something). */}
          <button
            type="button"
            onClick={pull}
            disabled={pulling}
            className="rounded-interactive border border-accent-line bg-surface-hover px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:shadow-glow disabled:opacity-60"
          >
            {pulling ? "Pulling…" : "Pull now"}
          </button>
        </div>
      </div>

      {/* The run banner. With the pull happening in the background, a quiet
          night, a run still going, and a run that died all look like an inbox
          that did not change — so each one has to say which it is. */}
      {run && <RunBanner run={run} />}

      {error && (
        <p className="mt-4 rounded-interactive border border-line bg-surface px-3 py-2 text-[13px] text-ink">
          {error}
        </p>
      )}

      {/* The funnel. Sorting makes the TOP of the list worth reading; it does
          nothing about the two hundred and eighty rows below it, and a list
          that long reads as a chore in any order. These make it shorter.

          Nothing here is remembered between visits: a filter that silently
          persisted is how you conclude the feed stopped finding anything. */}
      {!loading && jobs.length > 0 && (
        <div className="mt-6 flex flex-wrap items-center gap-2">
          <div className="relative">
            <svg className="pointer-events-none absolute left-2.5 top-1/2 size-[13px] -translate-y-1/2 text-ink-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              value={filters.query}
              onChange={(e) => setFilter({ query: e.target.value })}
              placeholder="Search company or role"
              className="w-[210px] rounded-interactive border border-line bg-surface py-1.5 pl-8 pr-3 text-[12px] text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none"
            />
          </div>
          <FilterChip
            active={filters.newOnly}
            onClick={() => setFilter({ newOnly: !filters.newOnly })}
          >
            New only
          </FilterChip>
          <FilterChip
            active={filters.watchlistOnly}
            onClick={() => setFilter({ watchlistOnly: !filters.watchlistOnly })}
          >
            Watchlist only
          </FilterChip>
          {[60, 80].map((level) => (
            <FilterChip
              key={level}
              active={filters.minFit === level}
              onClick={() => setFilter({ minFit: filters.minFit === level ? 0 : level })}
            >
              Matches {level}%+
            </FilterChip>
          ))}
          <span className="ml-auto text-[12px] text-ink-muted">
            {groups.length === jobs.length
              ? `${groups.length} to review`
              : `${groups.length} of ${jobs.length}`}
          </span>
        </div>
      )}

      {loading ? (
        <ul className="mt-6 flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-[92px] animate-pulse rounded-frame border border-line bg-surface motion-reduce:animate-none" />
          ))}
        </ul>
      ) : groups.length === 0 ? (
        // Distinct from an empty inbox: you filtered these away, and the fix is
        // a click rather than another pull.
        jobs.length > 0 ? (
          <div className="mt-8 rounded-frame border border-line bg-surface px-6 py-10 text-center">
            <p className="text-[15px] text-ink">Nothing matches those filters</p>
            <button
              type="button"
              onClick={() => setFilter(NO_FILTERS)}
              className="mx-auto mt-3 block rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-soft hover:border-line-strong"
            >
              Clear filters
            </button>
          </div>
        ) : (
        // Named, not generic: an empty inbox because nothing was found and an
        // empty inbox because you cleared it are different situations.
        <div className="mt-10 rounded-frame border border-line bg-surface px-6 py-12 text-center">
          <p className="text-[15px] text-ink">Nothing waiting</p>
          <p className="mx-auto mt-2 max-w-[380px] text-[13px] leading-relaxed text-ink-soft">
            Either the last pull found nothing new, or you have worked through
            everything it did. Pull now to check again.
          </p>
        </div>
        )
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {shown.map((group) => (
            <Row
              key={group.lead.id}
              job={group.lead}
              // Near-identical postings from the same employer, folded in. Kept
              // reachable rather than dropped: two that look alike are
              // sometimes different roles, and a quietly deleted one is a job
              // you wanted with no way to notice.
              others={group.others}
              applications={applications}
              // New means "found by the most recent pull". Compared against the
              // run rather than a timestamp so it survives you leaving the page
              // and coming back, and so it resets the moment you pull again.
              isNew={run !== null && group.lead.run_id === run.id}
              busy={busy === group.lead.id}
              onAccept={(posting) => accept(group.lead, posting)}
              onDismiss={() => dismiss(group.lead)}
              onAcceptOther={(job, posting) => accept(job, posting)}
              onDismissOther={(job) => dismiss(job)}
            />
          ))}
        </ul>
      )}

      {/* Paging so a session is a sitting rather than a scroll. Fifteen
          decisions is roughly where attention goes, and a page you can finish
          is the difference between triaging and giving up. */}
      {pages > 1 && (
        <div className="mt-6 flex items-center justify-between gap-4 border-t border-line pt-5">
          <button
            type="button"
            onClick={() => setPage(current - 1)}
            disabled={current === 0}
            className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-[12px] text-ink-muted">
            {current * PAGE_SIZE + 1}–{Math.min((current + 1) * PAGE_SIZE, groups.length)} of{" "}
            {groups.length}
          </span>
          <button
            type="button"
            onClick={() => setPage(current + 1)}
            disabled={current >= pages - 1}
            className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
