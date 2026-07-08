# Decisions

Short record of what was decided and why, so any future session (mine or Claude Code's) can catch up without rereading everything. One or two lines each. Newest at the bottom.

## v1 data model and scope (July 8, 2026)

- One table, not two. Internships and scholarships share a single `applications` table with a `type` discriminator column. Reason: the subtypes differ by data, not behavior, and the whole point is one unified pipeline. Two tables would double the work for every feature. Revisit only if a subtype ever needs genuinely different processing.
- Types for v1: internship and scholarship only. Fellowship, research, and grant get added when I actually apply to one. Not modeling hypotheticals.
- Queryable fields are real columns; display only fields go in a JSON column. Anything I filter, sort, or search by (deadline, status, type, priority, organization, role_or_program) is a real typed column. Messy or evolving parser output goes in a `jd_parsed` JSON blob. Promote a JSON field to a real column the day I actually filter on it, which is a one column migration.
- No money columns yet. Salary and award amount live in `jd_parsed` for now. Promote to a column when I actually want to sort by money, not before.
- One shared status enum, superset of both types. Values: discovered, shortlisted, drafting, ready, applied, applied_confirmed, recruiter_engaged, phone_screen, technical_interview, onsite, offer, accepted, declined, rejected, ghosted, missed_deadline. No transition validation in v1; that state machine is deferred to v2.
- Hard delete for v1. Single careful user. Add soft delete only if I fat finger a row and regret it.
- UUID primary keys stored as VARCHAR(36). Reason: IDs don't leak how many applications I have and don't collide if n8n ever creates rows. Cost is uglier URLs, acceptable.
- created_at and updated_at timestamps from the start. Cheap, and I'll want "added this week" and "stale 30 days" later.
- SQLite for v1. Postgres later, only when I deploy for real and need concurrency or pgvector.
- Build order: CRUD loop first (create, read, update, list by hand), JD parsing and AI second. One unknown at a time.
- Deferred on purpose, do not build yet: resume_versions table (v2), timeline_events table (v4), essays table and pgvector (v6 or never), match scoring, materials checklist, contacts, deployment, auth. These arrive with the version that owns them.