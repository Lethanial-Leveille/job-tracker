// The application's status history, shown on the Overview tab. This is what
// makes "interviewed, then rejected" legible: a single status field would read
// "Rejected" with no sign it ever got to an interview. Refetches when the
// application's updated_at changes, so a status change here or an accepted email
// suggestion shows up right away.
//
// Calm data on dark, no purple — a plain vertical timeline.

import { useEffect, useState } from "react";
import type { Application, StatusEvent } from "../../lib/types";
import { deleteTimelineEvent, listApplicationTimeline } from "../../lib/api";
import { statusLabel } from "../../lib/format";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function StatusTimeline({ application }: { application: Application }) {
  const [events, setEvents] = useState<StatusEvent[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function remove(eventId: string) {
    setBusyId(eventId);
    try {
      await deleteTimelineEvent(application.id, eventId);
      setEvents((prev) => (prev ?? []).filter((e) => e.id !== eventId));
    } catch {
      // Leave the entry in place if the delete failed.
    } finally {
      setBusyId(null);
    }
  }

  useEffect(() => {
    let live = true;
    setEvents(null);
    listApplicationTimeline(application.id)
      .then((e) => live && setEvents(e))
      .catch(() => live && setEvents([]));
    return () => {
      live = false;
    };
    // updated_at changes on every status change, so the history stays current.
  }, [application.id, application.updated_at]);

  return (
    <section className="flex flex-col gap-3.5">
      <div className="flex items-center gap-2 text-[10.5px] font-semibold uppercase tracking-[0.13em] text-ink-muted">
        Status history
        <span className="h-px flex-1 bg-line" />
      </div>

      {events === null ? (
        <p className="text-[12px] text-ink-muted">Loading…</p>
      ) : events.length === 0 ? (
        <p className="text-[12px] text-ink-muted">
          No status changes recorded yet.
        </p>
      ) : (
        <ol className="flex flex-col">
          {events.map((e, i) => (
            <li key={e.id} className="group flex gap-3">
              {/* Dot + connector line down to the next entry. */}
              <div className="flex flex-col items-center">
                <span className="mt-1.5 size-2 shrink-0 rounded-full bg-ink-muted" />
                {i < events.length - 1 && <span className="w-px flex-1 bg-line" />}
              </div>
              <div className="flex flex-1 items-start justify-between gap-2 pb-4">
                <div>
                  <div className="text-[13px] text-ink">
                    {e.from_status === null
                      ? `Added as ${statusLabel(e.to_status)}`
                      : `${statusLabel(e.from_status)} → ${statusLabel(e.to_status)}`}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-muted">
                    <span>{fmtDate(e.created_at)}</span>
                    {e.source === "email" && (
                      <span className="rounded-full border border-line px-1.5 py-0.5 text-[10px]">
                        from email
                      </span>
                    )}
                  </div>
                </div>
                {/* Prune a misclick. Hidden until hover/focus so the log stays
                    calm; deleting an entry only tidies history, not the status. */}
                <button
                  type="button"
                  onClick={() => remove(e.id)}
                  disabled={busyId === e.id}
                  aria-label="Remove this history entry"
                  className="shrink-0 rounded-interactive p-1 text-ink-muted opacity-0 transition-opacity hover:text-ink focus-visible:opacity-100 group-hover:opacity-100 disabled:opacity-40"
                >
                  <svg className="size-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
