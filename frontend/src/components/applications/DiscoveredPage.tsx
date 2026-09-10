import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Application, DiscoveredJob, Eligibility } from "../../lib/types";
import { acceptDiscovered, dismissDiscovered } from "../../lib/api";
import { useDiscovered } from "../../lib/useDiscovered";
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
  if (eligibility.verdict === "mismatch") {
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

function Row({
  job,
  applications,
  onAccept,
  onDismiss,
  busy,
}: {
  job: DiscoveredJob;
  applications: Application[];
  onAccept: () => void;
  onDismiss: () => void;
  busy: boolean;
}) {
  const note = eligibilityNote(job.eligibility, job.enriched_at);
  const maybe = (job.possible_application_ids ?? [])
    .map((id) => applications.find((a) => a.id === id))
    .filter((a): a is Application => a !== undefined);

  return (
    <li className="rounded-frame border border-line bg-surface px-5 py-4 transition-colors hover:border-line-strong">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
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
            {job.role_family && <Chip>{job.role_family}</Chip>}
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
            onClick={onAccept}
            disabled={busy}
            className="rounded-interactive border border-line-strong bg-surface-hover px-3 py-1.5 text-[12.5px] font-medium text-ink transition-colors hover:border-accent-line disabled:opacity-50"
          >
            Track it
          </button>
        </div>
      </div>
    </li>
  );
}

export function DiscoveredPage({ applications, onChanged }: Props) {
  const { jobs, loading, error, pulling, lastPull, refetch, pull } = useDiscovered();
  const [busy, setBusy] = useState<string | null>(null);
  const navigate = useNavigate();

  async function accept(job: DiscoveredJob) {
    setBusy(job.id);
    try {
      const created = await acceptDiscovered(job.id);
      await refetch();
      // Refresh the pipeline upstairs too, or the new row is missing from the
      // list you land on.
      onChanged();
      navigate(`/applications/${created.id}`);
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
        {/* The one primary action on the screen, and so the one place purple
            appears (docs/design.md: purple should feel like it costs something). */}
        <button
          type="button"
          onClick={pull}
          disabled={pulling}
          className="rounded-interactive border border-accent-line bg-surface-hover px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:shadow-glow disabled:opacity-60"
        >
          {pulling ? "Pulling…" : "Pull now"}
        </button>
      </div>

      {pulling && (
        <p className="mt-4 text-[12.5px] text-ink-muted">
          Downloading the feed, then reading whatever is new. This takes a minute
          the first time.
        </p>
      )}

      {lastPull && !pulling && (
        <p className="mt-4 text-[12.5px] text-ink-muted">
          Last pull: {lastPull.staged} new, {lastPull.enriched} read,{" "}
          {lastPull.duplicates} already seen.
        </p>
      )}

      {error && (
        <p className="mt-4 rounded-interactive border border-line bg-surface px-3 py-2 text-[13px] text-ink">
          {error}
        </p>
      )}

      {loading ? (
        <ul className="mt-6 flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <li key={i} className="h-[92px] animate-pulse rounded-frame border border-line bg-surface motion-reduce:animate-none" />
          ))}
        </ul>
      ) : jobs.length === 0 ? (
        // Named, not generic: an empty inbox because nothing was found and an
        // empty inbox because you cleared it are different situations.
        <div className="mt-10 rounded-frame border border-line bg-surface px-6 py-12 text-center">
          <p className="text-[15px] text-ink">Nothing waiting</p>
          <p className="mx-auto mt-2 max-w-[380px] text-[13px] leading-relaxed text-ink-soft">
            Either the last pull found nothing new, or you have worked through
            everything it did. Pull now to check again.
          </p>
        </div>
      ) : (
        <ul className="mt-6 flex flex-col gap-3">
          {jobs.map((job) => (
            <Row
              key={job.id}
              job={job}
              applications={applications}
              busy={busy === job.id}
              onAccept={() => accept(job)}
              onDismiss={() => dismiss(job)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
