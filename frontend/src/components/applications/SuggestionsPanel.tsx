// The review queue for status suggestions from the Gmail pipeline. Shows only
// when there is something pending, above the applications table. Each item shows
// the email that triggered it and the proposed status change; nothing is applied
// until the user clicks — the frontend half of "propose, never decide".
//
// Three shapes, matching the backend: a resolved suggestion (one target, one
// Accept), an ambiguous one (pick which application), and an unmatched one
// (couldn't tie it to an application, so only Dismiss).

import { useState } from "react";
import type { Application, StatusSuggestion } from "../../lib/types";
import { acceptSuggestion, dismissSuggestion } from "../../lib/api";
import { statusLabel } from "../../lib/format";
import { useSuggestions } from "../../lib/useSuggestions";

const primaryBtn =
  "rounded-interactive bg-accent px-3 py-1.5 text-[13px] font-medium text-ink transition-shadow transition-colors hover:bg-accent-hover hover:shadow-glow active:bg-accent-press disabled:opacity-60 disabled:shadow-none";
const secondaryBtn =
  "rounded-interactive border border-line bg-base px-3 py-1.5 text-[13px] font-medium text-ink-soft transition-colors hover:border-line-strong hover:text-ink disabled:opacity-40";

interface Props {
  applications: Application[];
  // Called after an accept changes an application's status, so the list refreshes.
  onResolved: () => void;
}

export function SuggestionsPanel({ applications, onResolved }: Props) {
  const { suggestions, loading, refetch } = useSuggestions();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Nothing to review (or still loading the first time) → render nothing, so the
  // panel never shows an empty card.
  if (loading || suggestions.length === 0) return null;

  const appName = (id: string): string => {
    const app = applications.find((a) => a.id === id);
    return app ? `${app.organization} — ${app.role_or_program}` : "an application";
  };

  async function run(action: () => Promise<unknown>, id: string) {
    setBusyId(id);
    setError(null);
    try {
      await action();
      await refetch(); // drop it from the queue
      onResolved(); // an accepted status change means the list is now stale
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="rounded-frame border border-line-strong bg-surface p-5">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ink">Needs review</h2>
        <span className="rounded-full border border-line px-2 py-0.5 text-[11px] text-ink-muted">
          {suggestions.length}
        </span>
        <p className="ml-1 text-[12.5px] text-ink-muted">
          Status changes from your inbox — nothing is applied until you accept.
        </p>
      </div>

      {error && <p className="mt-3 text-[13px] text-ink-soft">{error}</p>}

      <div className="mt-4 flex flex-col gap-3">
        {suggestions.map((s) => (
          <SuggestionItem
            key={s.id}
            suggestion={s}
            appName={appName}
            busy={busyId === s.id}
            onAccept={(appId) =>
              run(() => acceptSuggestion(s.id, appId), s.id)
            }
            onDismiss={() => run(() => dismissSuggestion(s.id), s.id)}
          />
        ))}
      </div>
    </section>
  );
}

function SuggestionItem({
  suggestion: s,
  appName,
  busy,
  onAccept,
  onDismiss,
}: {
  suggestion: StatusSuggestion;
  appName: (id: string) => string;
  busy: boolean;
  onAccept: (applicationId?: string) => void;
  onDismiss: () => void;
}) {
  const label = statusLabel(s.suggested_status);
  const resolved = s.application_id !== null;
  const candidates = s.candidate_application_ids ?? [];

  return (
    <div className="flex flex-col gap-2 rounded-interactive border border-line bg-base p-4">
      {/* Evidence: the email that triggered this. */}
      {s.email && (
        <div className="text-[12.5px] leading-relaxed text-ink-muted">
          <span className="text-ink-soft">
            {s.email.from_name || s.email.from_email}
          </span>
          {s.email.subject ? ` — ${s.email.subject}` : ""}
          {s.email.snippet ? (
            <span className="line-clamp-2 text-ink-muted">{s.email.snippet}</span>
          ) : null}
        </div>
      )}

      {/* Proposed change + reason. */}
      <div className="text-sm text-ink">
        {resolved
          ? `Mark ${appName(s.application_id as string)} as ${label}`
          : candidates.length > 0
            ? `Mark as ${label} — which application?`
            : `Suggests ${label}, but no application matched.`}
      </div>
      <div className="text-[12px] text-ink-muted">{s.reason}</div>

      {/* Controls. */}
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {resolved && (
          <button type="button" disabled={busy} onClick={() => onAccept()} className={primaryBtn}>
            {busy ? "Working…" : "Accept"}
          </button>
        )}
        {!resolved &&
          candidates.map((id) => (
            <button
              key={id}
              type="button"
              disabled={busy}
              onClick={() => onAccept(id)}
              className={primaryBtn}
            >
              {appName(id)}
            </button>
          ))}
        <button type="button" disabled={busy} onClick={onDismiss} className={secondaryBtn}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
