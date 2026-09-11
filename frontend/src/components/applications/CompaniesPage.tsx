import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type {
  Ats,
  IdentifyResult,
  TargetCompany,
  TargetCompanyInput,
} from "../../lib/types";
import {
  atsRequirements,
  createCompany,
  deleteCompany,
  identifyBoard,
  listCompanies,
  updateCompany,
} from "../../lib/api";

// The watchlist behind direct board polling: employers whose own job boards get
// read every night, alongside the aggregator feed.
//
// The form is the whole point of this screen, and it is awkward on purpose.
// Three of the five systems name a board with one string and two need three, so
// which boxes appear depends on which system you pick. The alternative — five
// boxes always, three of them meaningless — is how a company gets saved in a
// shape that returns nothing every night without ever saying so.
//
// Which fields are required comes from the API rather than a copy here, so the
// form and the backend validator cannot drift apart.

const ATS_OPTIONS: { value: Ats; label: string }[] = [
  { value: "greenhouse", label: "Greenhouse" },
  { value: "lever", label: "Lever" },
  { value: "ashby", label: "Ashby" },
  { value: "workday", label: "Workday" },
  { value: "oracle", label: "Oracle" },
];

// What to call each field on each system, and where to find it. "Board" means
// three different things across these vendors, and a label that says "board" is
// useless when the thing you need is a tenant buried in a hostname.
const HELP: Record<string, Record<string, { label: string; hint: string }>> = {
  greenhouse: {
    board: { label: "Board token", hint: "boards.greenhouse.io/THIS" },
  },
  lever: { board: { label: "Company slug", hint: "jobs.lever.co/THIS" } },
  ashby: { board: { label: "Organization", hint: "jobs.ashbyhq.com/THIS" } },
  workday: {
    host: { label: "Hostname", hint: "acme.wd5.myworkdayjobs.com" },
    board: { label: "Tenant", hint: "the first part of the hostname" },
    site: { label: "Site id", hint: "external_experienced" },
  },
  oracle: {
    host: { label: "Hostname", hint: "careers.acme.com" },
    site: { label: "Site number", hint: "CX_1001" },
  },
};

const FIELD =
  "rounded-interactive border border-line bg-base px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:shadow-glow focus:outline-none";
const LABEL =
  "flex flex-col gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.1em] text-ink-muted";

const BLANK: TargetCompanyInput = { name: "", ats: "greenhouse", board: "", host: "", site: "" };

export function CompaniesPage() {
  const [companies, setCompanies] = useState<TargetCompany[]>([]);
  const [required, setRequired] = useState<Record<string, string[]>>({});
  const [draft, setDraft] = useState<TargetCompanyInput>(BLANK);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [link, setLink] = useState("");
  const [checking, setChecking] = useState(false);
  // What the pasted link turned out to be, kept so the form can show what it
  // found rather than silently rearranging itself.
  const [found, setFound] = useState<IdentifyResult | null>(null);

  const load = useCallback(async () => {
    try {
      const [rows, reqs] = await Promise.all([listCompanies(), atsRequirements()]);
      setCompanies(rows);
      setRequired(reqs);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load the watchlist");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const fields = required[draft.ats] ?? [];

  async function check() {
    setChecking(true);
    setError(null);
    setFound(null);
    try {
      const result = await identifyBoard(link);
      setFound(result);
      // Fill the form from what was found. The name is left alone: a board does
      // not reliably say who it belongs to, and the name you type is the one
      // you will recognise in a list six weeks from now.
      setDraft({
        ...draft,
        ats: result.ats,
        board: result.board ?? "",
        host: result.host ?? "",
        site: result.site ?? "",
      });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not read that link");
    } finally {
      setChecking(false);
    }
  }

  async function add() {
    setSaving(true);
    setError(null);
    try {
      // Only send what this system uses. Sending empty strings for the others
      // would store blanks that read as configured and are not.
      const input: TargetCompanyInput = { name: draft.name.trim(), ats: draft.ats };
      for (const field of fields) {
        input[field as "board" | "host" | "site"] =
          (draft[field as "board" | "host" | "site"] ?? "").trim();
      }
      await createCompany(input);
      setDraft(BLANK);
      setLink("");
      setFound(null);
      await load();
    } catch (err: unknown) {
      // The backend names the exact field, so it is shown verbatim.
      setError(err instanceof Error ? err.message : "Could not save that company");
    } finally {
      setSaving(false);
    }
  }

  async function toggle(company: TargetCompany) {
    await updateCompany(company.id, { active: !company.active });
    await load();
  }

  async function remove(company: TargetCompany) {
    await deleteCompany(company.id);
    await load();
  }

  return (
    <div className="mx-auto max-w-[880px] px-2 pb-20 pt-8">
      <Link
        to="/discovered"
        className="inline-flex items-center gap-2 text-[12.5px] text-ink-muted hover:text-ink"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="m15 18-6-6 6-6" />
        </svg>
        Discovered
      </Link>

      <h1 className="mt-4 font-serif text-[28px] font-semibold text-ink">Watchlist</h1>
      <p className="mt-1.5 max-w-[560px] text-[13px] leading-relaxed text-ink-soft">
        Companies whose own job boards get read every night, alongside the feed.
        Direct boards are faster and everything they return is somewhere you
        chose, so almost nothing needs dismissing.
      </p>

      {/* Add form */}
      <div className="mt-7 rounded-frame border border-line bg-surface px-5 py-5">
        {/* The fast path. Knowing that Stripe's Greenhouse token is "stripe" and
            Adobe's Workday site is "external_experienced" is a real errand, per
            company, and getting one wrong makes an entry that returns nothing
            every night without saying why. Pasting the link you were already
            looking at removes the errand. */}
        <label className={LABEL}>
          Paste a careers link
          <div className="flex gap-2">
            <input
              className={`${FIELD} flex-1`}
              value={link}
              onChange={(e) => setLink(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && link.trim() !== "") check();
              }}
              placeholder="https://boards.greenhouse.io/rivian"
            />
            <button
              type="button"
              onClick={check}
              disabled={checking || link.trim() === ""}
              className="shrink-0 rounded-interactive border border-line-strong bg-surface-hover px-3 py-2 text-[12.5px] text-ink transition-colors hover:border-accent-line disabled:opacity-50"
            >
              {checking ? "Reading…" : "Check"}
            </button>
          </div>
          <span className="text-[10px] font-normal normal-case tracking-normal text-ink-muted">
            Greenhouse, Lever, Ashby, Workday or Oracle. Fills in the rest below.
          </span>
        </label>

        {/* What the board actually has, before you commit to watching it. Zero
            is not necessarily wrong, which is why this reports rather than
            blocks. */}
        {found && (
          <div className="mt-3 rounded-interactive border border-line bg-base px-3.5 py-2.5">
            <p className="text-[12.5px] text-ink">
              {found.ats} board,{" "}
              {found.internships === 0
                ? "no internships posted right now"
                : `${found.internships} internship${found.internships === 1 ? "" : "s"} posted right now`}
              .
            </p>
            {found.sample.length > 0 && (
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">
                {found.sample.join(" · ")}
              </p>
            )}
          </div>
        )}

        <div className="my-5 flex items-center gap-4 text-[10.5px] uppercase tracking-[0.16em] text-ink-muted">
          <span className="h-px flex-1 bg-line" />
          Or fill it in
          <span className="h-px flex-1 bg-line" />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className={LABEL}>
            Company
            <input
              className={FIELD}
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              placeholder="Rivian"
            />
          </label>
          <label className={LABEL}>
            System
            <select
              className={FIELD}
              value={draft.ats}
              onChange={(e) => setDraft({ ...draft, ats: e.target.value as Ats })}
            >
              {ATS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>

          {/* Only the boxes this system actually uses. */}
          {fields.map((field) => {
            const help = HELP[draft.ats]?.[field];
            return (
              <label key={field} className={LABEL}>
                {help?.label ?? field}
                <input
                  className={FIELD}
                  value={draft[field as "board" | "host" | "site"] ?? ""}
                  onChange={(e) =>
                    setDraft({ ...draft, [field]: e.target.value })
                  }
                  placeholder={help?.hint}
                />
                <span className="text-[10px] font-normal normal-case tracking-normal text-ink-muted">
                  {help?.hint}
                </span>
              </label>
            );
          })}
        </div>

        {error && (
          <p className="mt-4 rounded-interactive border border-line-strong bg-surface-hover px-3 py-2 text-[12.5px] text-ink">
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={add}
          disabled={saving || draft.name.trim() === ""}
          className="mt-5 rounded-interactive border border-accent-line bg-surface-hover px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:shadow-glow disabled:opacity-50"
        >
          {saving ? "Adding…" : "Add company"}
        </button>
      </div>

      {/* The list */}
      {loading ? (
        <p className="mt-8 text-[13px] text-ink-muted">Loading…</p>
      ) : companies.length === 0 ? (
        <div className="mt-8 rounded-frame border border-line bg-surface px-6 py-10 text-center">
          <p className="text-[15px] text-ink">No companies watched yet</p>
          <p className="mx-auto mt-2 max-w-[420px] text-[13px] leading-relaxed text-ink-soft">
            Until you add one, discovery runs on the aggregator feed alone. Add a
            company and its board gets read every night too.
          </p>
        </div>
      ) : (
        <ul className="mt-8 flex flex-col gap-2">
          {companies.map((company) => (
            <li
              key={company.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-frame border border-line bg-surface px-4 py-3"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className={`text-[14px] ${company.active ? "text-ink" : "text-ink-muted"}`}>
                    {company.name}
                  </span>
                  <span className="text-[11px] text-ink-muted">{company.ats}</span>
                  {!company.active && (
                    <span className="rounded-interactive border border-line px-1.5 py-0.5 text-[10.5px] text-ink-muted">
                      paused
                    </span>
                  )}
                </div>
                {/* Shown because a board failing quietly for a fortnight is
                    otherwise invisible: the run finishes and the inbox is just
                    thinner than it should be. */}
                {company.last_error && (
                  <p className="mt-1 text-[11.5px] text-ink-soft">{company.last_error}</p>
                )}
              </div>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() => toggle(company)}
                  className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft"
                >
                  {company.active ? "Pause" : "Resume"}
                </button>
                <button
                  type="button"
                  onClick={() => remove(company)}
                  className="rounded-interactive border border-line px-3 py-1.5 text-[12.5px] text-ink-muted transition-colors hover:border-line-strong hover:text-ink-soft"
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
