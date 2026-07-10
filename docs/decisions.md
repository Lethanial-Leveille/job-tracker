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