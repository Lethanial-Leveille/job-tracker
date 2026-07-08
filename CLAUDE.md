# CLAUDE.md

This file gives Claude Code the context it needs to be helpful in this repo. Read it fully before responding to any task in this codebase.

---

## About the developer

Lee Leveille. UF Computer Engineering, Class of 2029. Currently a freshman, on campus Fall 2026. Confirmed Summer 2026 SWE internship at Fuzzy AI in Singapore.

Career target: embedded and firmware engineering at Apple, Google, Amazon, NVIDIA, Qualcomm, or Tesla. Personal brand: full stack hardware to cloud engineer.

**This project is a learning project as much as a production tool.** Lee is building it to:

1. Use it himself to track real internship and scholarship applications through Fall 2026 application season.
2. Have a flagship full stack portfolio piece for FAANG and embedded role applications.
3. Learn FastAPI, SQLAlchemy, React + TypeScript, Postgres, and production deployment on real infrastructure.

**He values honesty over encouragement. Don't sugarcoat. Don't agree to please.** If a design decision is bad, say so. If a simpler approach exists, name it.

Style: avoid hyphens in compound modifiers when possible (write "full stack" not "full-stack"). No em dashes.

**Lee is relatively new to CS/CPE terminology.** Always define technical terms in plain English before using them in tradeoff discussions. Never assume familiarity with terms like UUID, JSONB, async/sync, ORM, dependency injection, etc.

---

## Teaching mode is the default

This repo is a learning vehicle. That means:

- **Explain before you write.** When asked to implement something, walk through the approach in plain English first. Name the pattern (dependency injection, Pydantic validation, etc.). Then ask if it makes sense before writing code.
- **Name alternatives.** When there is a real choice (SQLAlchemy ORM vs raw SQL, async vs sync endpoints, useState vs useReducer), surface the alternatives and the tradeoff in 2 to 4 sentences. Then make a recommendation.
- **One file per turn by default.** Don't generate ten files at once unless explicitly asked. Lee needs to read what you write.
- **Flag concepts to learn.** When you use a non obvious pattern (FastAPI Depends, Pydantic field validators, React useEffect cleanup, Vite proxy config), call it out: "this is a FastAPI dependency injection pattern, here's why we use it."
- **Never invent facts about Lee.** His resume content lives in `backend/data/master_resume.yaml`. The renderer can reorder and rephrase, but no new claims, technologies, or metrics.

When in doubt, ask before generating.

---

## Project: job-tracker

A single user job and scholarship application tracker. Tracks discovery → application → interview → offer pipeline for internships, scholarships, fellowships, and research grants (no full time roles — Lee is a freshman). Includes AI assisted resume tailoring, essay drafting via Notion, and integration with n8n on a Raspberry Pi for Gmail and calendar automation.

Full design brief lives in `docs/build-brief.md`.

---

## Stack

**Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic for migrations. Running on Python 3.14 in dev (compatible).
**Database:** SQLite for v1 and v2 (file at `backend/data/dev.db`). Migrating to Postgres at v3 or later.
**Frontend:** React 18, TypeScript, Vite, Tailwind CSS v4, dark theme.
**AI:** Anthropic Claude API. Default model `claude-sonnet-4-6` for parsing and routine tasks. `claude-opus-4-7` only for resume tailoring and essay drafts. Note: `claude-sonnet-4-7` does not exist yet — do not use it.
**Auth:** JWT, single user. Lee is the only account. Service token for n8n webhooks. NOT YET IMPLEMENTED — no auth middleware exists in v1.
**Deployment:** DigitalOcean droplet for v1 backend, Cloudflare Pages for frontend. Domain: `track.lethanial.com` (frontend), `api.track.lethanial.com` or proxied path for backend. NOT YET DEPLOYED.
**Storage:** DigitalOcean Spaces (S3 compatible) for resume PDFs and cover letter files. NOT YET IMPLEMENTED.
**Background jobs:** n8n on Raspberry Pi calls the tracker's REST API. No Celery in v1. NOT YET INTEGRATED.
**Package manager:** `uv` for Python (installed at `~/.local/bin/uv`). `npm` for frontend.

---

## Current state (as of May 3, 2026 — Session 2 complete)

### What is built and working

**Backend (v1 feature complete):**
- `applications` table in SQLite via Alembic migration (run and applied)
- `POST /applications` — only `posting_url` is required. Scrapes the URL via `requests` + BeautifulSoup, calls Claude to parse the JD, infers `organization`, `role_or_program`, and `type` automatically. Caller can override any inferred field.
- `GET /applications` — returns list, filterable by `status`, `type`, `priority`
- `GET /applications/{id}` — single application detail
- `PATCH /applications/{id}` — update status, notes, priority, deadline
- `DELETE /applications/{id}` — hard delete
- `/health` endpoint for uptime checks
- JD parser returns: `inferred_organization`, `inferred_role`, `inferred_type`, `required_skills`, `nice_to_haves`, `seniority`, `location`, `compensation`, `keywords`, `summary`
- `backend/tests/conftest.py` — pytest fixtures with in-memory SQLite test DB

**Frontend (v1 feature complete):**
- react-router-dom v6 installed; client-side routing across 4 routes
- Wakandan theme applied via Tailwind v4 `@theme` tokens in `index.css`
- `frontend/src/App.tsx` — route tree (`/`, `/applications`, `/applications/new`, `/applications/:id`), nav bar with home link and "+ New Application" button
- `frontend/src/pages/ApplicationList.tsx` — rethemed table, row click navigates to detail view
- `frontend/src/pages/ApplicationDetail.tsx` — full detail view: parsed JD (summary, required skills, nice-to-haves, seniority, location, comp, keywords), metadata card, view/edit mode toggle, PATCH on save, delete in edit mode, gold styling for offer and accepted states
- `frontend/src/pages/AddApplication.tsx` — URL form with optional override fields, full-screen loading state during Claude parse, navigates to detail view on success
- Full stack v1 confirmed working end to end

### What is NOT built yet (remaining v1 work)

- JWT authentication (backend middleware + frontend token handling)
- DigitalOcean deployment — `track.lethanial.com` not yet live
- `master_resume.yaml` — not yet created

### Known decisions made

**Session 1:**
- Sync SQLAlchemy (not async) for v1. Convert at v3 when Postgres arrives.
- UUID primary keys stored as `VARCHAR(36)` in SQLite.
- `JSON` column type for `jd_parsed` (becomes JSONB automatically in Postgres via Alembic).
- `full_time` removed from `ApplicationType` — Lee is a freshman, irrelevant until senior year.
- hatchling build backend for `pyproject.toml` (setuptools had compatibility issues with Python 3.14).
- Tailwind CSS v4 (not v3) — no config file needed, just a Vite plugin.

**Session 2:**
- react-router-dom v6 for routing. `<BrowserRouter>` in `main.tsx`, route tree in `App.tsx`.
- Wakandan theme tokens defined in `@theme` block in `index.css` — no config file, Tailwind v4 generates utility classes from CSS custom properties.
- Primary accent `#8B5CF6` (violet-500), not `#7C3AED` — brighter, more legible on the near-black background.
- Add form is its own page at `/applications/new`, not a modal — loading state is cleaner at full-screen during the 5-10 second Claude parse.
- Edit mode on detail view: explicit Edit/Save/Cancel buttons, not inline auto-save — deliberate and matches "never auto-submit" spirit.
- Status update uses a full dropdown of all 15 statuses for v1. Transition logic (only valid next states) deferred to v2.

---

## Repo structure

```
job-tracker/
├── CLAUDE.md                      ← this file (gitignored)
├── docs/
│   └── build-brief.md             ← full design doc (gitignored)
├── backend/
│   ├── main.py                    ← FastAPI app entry, lifespan context manager
│   ├── config.py                  ← pydantic-settings, reads .env
│   ├── database.py                ← SQLAlchemy engine, session, Base, get_db()
│   ├── models/
│   │   └── application.py        ← Application SQLAlchemy model
│   ├── schemas/
│   │   └── application.py        ← ApplicationCreate, ApplicationUpdate, ApplicationResponse
│   ├── routers/
│   │   └── applications.py       ← all 5 CRUD endpoints
│   ├── services/
│   │   └── jd_parser.py          ← scrapes URL, calls Claude, returns (jd_text, jd_parsed)
│   ├── data/
│   │   └── dev.db                ← SQLite database (gitignored)
│   ├── alembic/
│   │   └── versions/             ← first migration: create applications table (applied)
│   ├── tests/
│   │   └── conftest.py           ← in-memory test DB + TestClient fixtures
│   └── pyproject.toml            ← dependencies, hatchling build, ruff + black config
├── frontend/
│   ├── src/
│   │   ├── App.tsx               ← BrowserRouter route tree (4 routes), nav bar
│   │   ├── index.css             ← Tailwind v4 @theme Wakandan tokens + glow-accent utility
│   │   ├── main.tsx              ← React entry point, BrowserRouter wrapper
│   │   ├── pages/
│   │   │   ├── ApplicationList.tsx  ← list view, row click navigates to detail
│   │   │   ├── ApplicationDetail.tsx ← detail view, parsed JD, view/edit mode, PATCH, delete
│   │   │   └── AddApplication.tsx   ← URL form, optional overrides, loading state, POST
│   │   └── lib/
│   │       ├── api.ts            ← typed fetch wrappers for all endpoints
│   │       └── types.ts          ← TypeScript mirrors of backend Pydantic types
│   ├── public/
│   │   └── favicon.svg
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts            ← Tailwind plugin + /api proxy to :8000
└── .gitignore
```

---

## Dev workflow

**Backend:**
```bash
cd backend
source .venv/bin/activate          # venv already created with uv
uvicorn main:app --reload
```
Backend runs on `http://localhost:8000`. OpenAPI docs at `/docs`.
Secrets live in `backend/.env` (gitignored). Required keys: `ANTHROPIC_API_KEY`, `JWT_SECRET`.

**Frontend:**
```bash
cd frontend
npm run dev
```
Frontend runs on `http://localhost:5173`. Vite proxies `/api/*` to the backend automatically.

**Run both:** two terminals side by side.

**Migrations (when you add a column or table):**
```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

---

## Conventions

**Python:**
- Type hints everywhere. No bare `def foo(x):`. Always `def foo(x: str) -> dict:`.
- Pydantic models for all request and response bodies. Never accept raw dicts.
- SQLAlchemy 2.0 style (`select(Model).where(...)`), not legacy `Query` API.
- Sync endpoints for v1. Async when we move to Postgres at v3.
- Dependency injection via `Depends()` for DB sessions and auth.
- Errors raise `HTTPException` with status code and clear detail.

**TypeScript:**
- Strict mode on. No `any` without a comment explaining why.
- API client in `frontend/src/lib/api.ts` with typed wrappers for each endpoint.
- Types manually maintained in `frontend/src/lib/types.ts` — sync with backend schemas when they change.
- Functional components only, hooks for state. No class components.

**Git:**
- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`).
- Short one-line commit messages. No body paragraph.
- No `Co-Authored-By` trailer.

**Style:**
- Backend: ruff + black, configured in `pyproject.toml`.
- Frontend: eslint, configured in `eslint.config.js`.

---

## Hard rules

1. **Never auto submit anything.** The tracker drafts resumes, drafts cover letters, drafts followup emails. Lee reviews and submits manually. Always.
2. **Never invent resume content.** The tailoring step can reorder and rephrase. No new metrics, technologies, or claims.
3. **Never store credentials in code.** Use `.env`, never commit it. `config.py` reads via `pydantic-settings`.
4. **Never write to the production DB from a test.** Tests use a separate SQLite file or in memory DB.
5. **Never bypass the renderer for resume PDFs.** All resume PDFs go through `services/resume_renderer/` so visual style is consistent.
6. **No telemetry to third parties.** Single user app. Application data stays on Lee's infrastructure.

---

## What "done" looks like for v1

- [x] `applications` table exists with status, type, organization, role, deadline, URL fields
- [x] `POST /applications` accepts a URL, scrapes JD, calls Claude, stores raw + parsed
- [x] `GET /applications` returns list, filterable by status and type
- [x] `PATCH /applications/{id}` updates status and notes
- [x] React frontend: detail view, add form, edit form
- [ ] Deployed to DigitalOcean. Reachable at `track.lethanial.com`. JWT auth working.
- [ ] At least one real application tracked end to end

---

## Design system

The tracker uses a Black Panther / Wakandan inspired theme. Premium, focused, slightly regal.

**Palette:**
- Background: `#0A0612` (near black, slight purple undertone)
- Surface: `#1A1428` (cards, modals, raised elements)
- Primary accent: `#8B5CF6` (buttons, focused inputs, links — violet-500, brighter than 7C3AED on the dark bg)
- Surface 2: `#241C38` (nested badges, secondary raised elements)
- Border: `#2D2440` (dividers, input borders)
- Hover/active: `#A78BFA`
- Body text: `#E5E7EB`
- Headings: pure white
- Gold accent for "win" states: `#D4AF37` (offers received, scholarships awarded — used sparingly)

**Tone:** sleek, dark, intentional. Subtle purple glow on focused inputs and active rows. No gradients unless they're nearly imperceptible. Silver/white typography on the dark purple ground does most of the visual work.

**Avoid:** Marvel iconography, vibranium-as-a-word, anything that crosses from "inspired by" into IP territory. Color and mood are the inspiration; the rest is just good design.

This identity is specific to the tracker. M.I.L.E.S./Nova stays JARVIS electric blue. The portfolio root is Omnitrix green. Each project gets its own visual identity tied to a fictional engineer/inventor; the consistency across projects is in typography, spacing, and quality bar, not color.

---

## How to engage with Lee

- Match his honesty. If he's about to do something dumb, say so directly.
- When he asks for code, ask first whether he wants you to write it or talk through the approach.
- Acknowledge when something is over engineered for the current stage. Recommend the simpler path.
- When in doubt about scope, default to less.
- Always define technical terms before using them in tradeoff discussions.

---

## References

- Build brief: `docs/build-brief.md`
- FastAPI docs: https://fastapi.tiangolo.com/
- SQLAlchemy 2.0 docs: https://docs.sqlalchemy.org/en/20/
- Anthropic API docs: https://docs.claude.com/

---

*Last updated: May 3, 2026 — Session 2. Frontend v1 feature complete. Full stack v1 done. Remaining: JWT auth, DigitalOcean deployment.*
