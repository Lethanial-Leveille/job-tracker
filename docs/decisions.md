# Decisions

Short record of what was decided and why, so any future session (mine or Claude Code's) can catch up without rereading everything. One or two lines each. Newest at the bottom.

## v1 data model and scope (July 8, 2026)

- One table, not two. Internships and scholarships share a single `applications` table with a `type` discriminator column. Reason: the subtypes differ by data, not behavior, and the whole point is one unified pipeline. Two tables would double the work for every feature. Revisit only if a subtype ever needs genuinely different processing.
- Types for v1: internship and scholarship only. Fellowship, research, and grant get added when I actually apply to one. Not modeling hypotheticals.
- Queryable fields are real columns; display only fields go in a JSON column. Anything I filter, sort, or search by (deadline, status, type, priority, organization, role_or_program) is a real typed column. Messy or evolving parser output goes in a `jd_parsed` JSON blob. Promote a JSON field to a real column the day I actually filter on it, which is a one column migration.
- No money columns yet. Salary and award amount live in `jd_parsed` for now. Promote to a column when I actually want to sort by money, not before.
- One shared status enum, superset of both types. Values (14, trimmed from the original 16): discovered, drafting, ready, applied, recruiter_engaged, phone_screen, technical_interview, onsite, offer, accepted, declined, rejected, ghosted, missed_deadline. No transition validation in v1; that state machine is deferred to v2.
  - Dropped `shortlisted` (July 10, 2026): overlaps with what `priority` already expresses ("real target" = priority high). Re-add if a distinct vetted-but-not-drafting state proves useful.
  - Dropped `applied_confirmed` (July 10, 2026): the applied-vs-confirmed gap only earns its keep in v4 when the n8n Gmail watcher auto-flips it on a receipt email. Maintaining it by hand in v1 is busywork. Re-add with that automation.
- Hard delete for v1. Single careful user. Add soft delete only if I fat finger a row and regret it.
- UUID primary keys stored as VARCHAR(36). Reason: IDs don't leak how many applications I have and don't collide if n8n ever creates rows. Cost is uglier URLs, acceptable.
- created_at and updated_at timestamps from the start. Cheap, and I'll want "added this week" and "stale 30 days" later.
- SQLite for v1. Postgres later, only when I deploy for real and need concurrency or pgvector.
- Build order: CRUD loop first (create, read, update, list by hand), JD parsing and AI second. One unknown at a time.
- Deferred on purpose, do not build yet: resume_versions table (v2), timeline_events table (v4), essays table and pgvector (v6 or never), match scoring, materials checklist, contacts, deployment, auth. These arrive with the version that owns them.

## v1 skeleton (July 8, 2026)

- No config.py in v1. DATABASE_URL is a hardcoded constant in `database.py` (`sqlite:///./data/dev.db`). Reason: v1 CRUD reads no secrets or env vars, so pydantic-settings earns its place only in v2 (JD parsing API key). Adding it now is scaffolding for scaffolding.
- venv is path-locked. A Python virtualenv hardcodes its absolute path into console scripts (uvicorn, pip, alembic) and symlinks, so moving the project folder breaks it (symptom: "bad interpreter: .../no such file or directory"). Fix: `cd backend && rm -rf .venv && ~/.local/bin/uv venv && source .venv/bin/activate && uv pip install fastapi uvicorn sqlalchemy alembic`. The .venv is gitignored build state, safe to delete and rebuild.

## v1 Application model + Alembic (July 10, 2026)

- Status enum trimmed to 14 (see above): dropped `shortlisted` and `applied_confirmed`.
- Alembic `env.py` uses `DATABASE_URL` imported from `database.py` as the single source of truth, not a second URL hardcoded in `alembic.ini`. Model is imported in env.py purely to register its table on `Base.metadata` (autogenerate sees nothing without it).
- `render_as_batch=True` set in env.py. Reason: SQLite can't real-ALTER columns; batch mode makes Alembic emulate ALTER by copy-and-swap. Not needed for the initial create, but v2 column adds would break without it.
- First migration `5a510583d8ee` creates the applications table. The stale dev.db from the pre-rebuild build (1 test row: CareDX internship, notes="string", old `top_target` priority, extra jd_text/match_score columns) was deleted and rebuilt fresh. Backup lives in the session scratchpad, not the repo.

## v1 CRUD: schemas, services, routes, tests (July 12, 2026)

- Pydantic schemas split by operation: `ApplicationBase` holds the shared human-set fields, with `Create`/`Update`/`Read` on top. `Create` allows `status` and `priority` (optional-with-default) so a row can be added already-applied or high-priority. `Update` is standalone with every field optional (partial PATCH). `jd_parsed` is read-only: in `Read`, absent from `Create`/`Update` since no parser exists in v1.
- Layering: routes stay thin (validate, call service, return); all DB logic lives in `services/`. Not-found handling chose "Option A": services return `Application | None`, routes raise `HTTPException(404)`. Keeps services HTTP-ignorant so a non-HTTP caller (n8n, tests) can reuse them.
- Sessions: services never open or close a session; `get_db` via `Depends()` owns the lifecycle. That decoupling is also what lets a test pass an in-memory session straight into a service.
- Update uses `model_dump(exclude_unset=True)` + a `setattr` loop so only fields the client actually sent are changed; unsent fields are never overwritten. No `db.add` on update (the fetched row is already session-tracked, so commit flushes the dirty changes). Delete returns 204 No Content.
- Tests: in-memory SQLite fixture in `tests/conftest.py` using `StaticPool` (one shared connection, or the `:memory:` tables vanish between connections). Service-level tests only, no route/TestClient tests in v1 (curl covers the HTTP layer by hand). First service function was written test-first; the update test specifically asserts unsent fields stay unchanged, guarding the `exclude_unset` behavior.

## v1 frontend: shell, list, CRUD UI (July 12, 2026)

- Stack in build: Vite + React 19 + TypeScript (strict) + Tailwind v4. Tailwind v4 is CSS-first (no `tailwind.config.js`); design tokens live in an `@theme` block in `frontend/src/index.css`, the single source of truth for the visual system. Utilities generate from token names (`--color-surface` becomes `bg-surface`).
- Scope discipline: built only what the v1 API backs. Omitted the mockup's summary cards, the sidebar pipeline counts, and the per-row location line (no location column exists). Future nav (Deadlines, Organizations, Documents, Analytics) renders disabled and tagged "Soon", never with invented counts. Promote any of these the day real data backs them.
- Display mappings live in `lib/format.ts`: `internship` shows as "Job", `scholarship` as-is; statuses shown granular and humanized ("Technical interview"), not collapsed into buckets, so a badge never misrepresents a row.
- Visual direction is in `docs/design.md` and the tokens, but polish is deliberately deferred (revamp later), function first. Purple stays scarce: primary action, active nav, selected row, focused input, links, and the offer badge, nowhere else.
- Data fetch is lifted to `App` via a `useApplications` hook so the sidebar count and the table share one fetch, not two. After any write the list refreshes via `refetch()`. Optimistic update (append locally, skip the round trip) is deferred, flagged as a LATER comment in the hook.
- One modal, `ApplicationFormModal`, serves both create and edit, switched by an optional `application` prop, so the eight fields exist once. Delete lives inside it in edit mode behind a `window.confirm` (v1 is hard delete, no undo). Clicking a row opens the edit modal pre-filled.
- HTTP is wrapped in `lib/api.ts` (list/create/update/delete); components never call `fetch` directly. `lib/types.ts` mirrors the backend Pydantic schemas by hand (manual sync in v1).
- Dev proxy: Vite rewrites `/api/*` to `http://localhost:8000/*`, stripping the `/api` prefix, because the backend serves routes without one. Frontend code always calls `/api/...`.
- v1 CRUD is now complete through the UI (create, read, update, delete). Next unknown, per the build-order rule, is v2: JD/URL parsing via the Claude API.

## v2 JD parsing: paste-text extraction (July 20, 2026)

- Scope: paste JD **text**, not a URL. URL fetching is deferred — LinkedIn, Greenhouse, and Workday postings are JavaScript-rendered or bot-blocked, so a plain HTTP GET returns a login wall, not the posting. Parsing pasted text is the valuable core; URL fetch is a separate, flaky subproblem for a later pass.
- `config.py` finally exists, using pydantic-settings, exactly as the v1-skeleton note predicted ("pydantic-settings earns its place only in v2"). v1 read no secrets; v2's `ANTHROPIC_API_KEY` is the first. `Settings` holds `anthropic_api_key` (required, no default so the app won't start without it) and `anthropic_model` (default `claude-haiku-4-5`, a tunable so the model swaps without code changes). `get_settings()` is an `@lru_cache` singleton injected via `Depends`, mirroring `get_db`.
- Model: `claude-haiku-4-5`, per vision's "cheaper capable model for parsing and routine work." Verified current against the API docs. One-line bump to `claude-sonnet-5` via the setting if extraction quality on a messy posting disappoints.
- Extraction method: **structured outputs** (`client.messages.parse(output_format=ParsedJob)`), not tool use. For pure "give me typed data back" extraction it's cleaner than forcing a tool call, and it fits the Pydantic-everywhere convention. Caveat that shaped the schema: structured outputs rejects length/number constraints, so `ParsedJob` fields stay plain-typed (no `Field(min_length=...)`).
- Two schemas, deliberately separate: `ParsedJob` is the AI's output shape (content); `ApplicationCreate` is the DB shape (structure). Same content-vs-format split as the resume design. Mapping between them is a distinct concern, kept out of the parser so parsing stays single-responsibility.
- `POST /applications/parse` returns a raw `ParsedJob` and never writes a row (hard rule #1: never auto-submit). It does **not** map to `ApplicationCreate`: `posting_url` is required on create and a pasted JD carries no URL, so the frontend pre-fills what it can and you add the URL and review before saving.
- Extras (`salary`, `location`, `summary`, `key_requirements`) are extracted but **not yet persisted**. Bundling them into the `jd_parsed` column is the deferred follow-up — it requires promoting `jd_parsed` from read-only to settable on `ApplicationCreate`, which the v1 schema comment intentionally forbids. Do that the day the extras earn their keep.
- Tests mock the Anthropic client (`patch("services.parsing.Anthropic")`). The service calls a paid, non-deterministic API, so the same "tests never touch external state" rule that gave us the in-memory DB now keeps the suite off the network. The real call is verified by hand against a live posting.
- Frontend: an "Autofill from a posting" paste box lives **inside the create modal** (create mode only), not a second button/modal — least new surface, and it keeps the human-in-the-loop review inside the flow that already exists. It fills type/organization/role_or_program/deadline; purple stays reserved for Save, so Autofill is a grey secondary action.