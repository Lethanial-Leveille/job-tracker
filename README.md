# Prowl

**Personal Recruiting and Opportunity Workflow Log.** A full stack job application tracker with Claude built into the steps that usually eat the most time: reading a posting, checking fit, tailoring a resume, and keeping statuses current from email.

Live at [tracker.lethanial.com](https://tracker.lethanial.com) (invite only, no public signup).

<!-- Screenshot: add a capture of the running app here, e.g. docs/screenshot.png -->

## Why it exists

I built Prowl to run my own internship search, and it is also the first real piece of software I've shipped to users (me and my mom). It has three jobs: a tool I use every day, a portfolio project, and a REST API that my home automation (n8n) talks to.

Two rules shape every feature:

- **Propose, never decide.** Prowl drafts and suggests, and I review and submit. It never applies to a job, sends an email, or changes an application's status on its own. Email updates and discovered jobs show up as suggestions I accept or dismiss with one click.
- **Never invent.** Resume tailoring can reorder and rephrase what's already in my master resume. It cannot add a metric, a technology, or a claim that isn't there. Fit checks only cite evidence the resume actually contains.

## Features

**Add a job from a link.** Paste a posting URL and Prowl pulls the text straight from the hiring system's own JSON (Workday, Greenhouse, Lever, Ashby) and falls back to reading the page for other sites. Claude then parses it into structured fields: role, deadline, location, pay, requirements. If Prowl can't get a trustworthy copy of the posting, it refuses instead of guessing. It checks for redirects, search pages dressed up as postings, and pages that are mostly config noise. Tested against 120 live postings with zero fake pulls.

**Resume tailoring with a locked format.** The master resume is structured data (a "bullet bank" of everything I've done). Claude picks and rephrases bullets for a specific posting, and a fixed Jinja + CSS template renders the PDF with WeasyPrint. The model never sees the template, so every resume looks identical no matter how many I generate, and it's checked to fit on one page. Each tailored version is saved against its application.

**Requirement matching.** For each requirement in a posting, Prowl reports whether my resume meets it, partly meets it, or misses it, and cites the resume line that backs up each match.

**Email status updates.** n8n polls Gmail and sends new messages to a webhook. Claude classifies each one (application received, assessment invite, interview invite, rejection, offer), matches it to an application, and stages a suggested status change. The status timeline records what actually happened, in the order it happened.

**Job discovery.** A nightly pull reads the SimplifyJobs internship listings and the job boards of companies I'm targeting directly, and filters them by term, degree level, graduation year eligibility, and recency. Anything I've already seen gets dropped before any paid AI call, and a classifier only sorts what's left by role type. Whatever survives waits in a review queue.

**Multi user, per user data.** JWT login, bcrypt passwords, and every query scoped to the signed in user. Each user has their own master resume, edited in a resume builder in the browser.

## Stack

| Layer | Tools |
| --- | --- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, `uv` |
| Database | PostgreSQL (SQLite works for early local dev) |
| AI | Anthropic Claude API with structured outputs. Haiku for parsing, matching, and classification, Opus for tailoring |
| Resume rendering | Jinja2 + WeasyPrint |
| Frontend | React 19, TypeScript (strict), Vite, Tailwind CSS v4, React Router |
| Automation | n8n (Gmail polling, scheduled discovery), authenticated with a service token |
| Infra | DigitalOcean droplet, Caddy, systemd, Cloudflare Tunnel, nightly `pg_dump` backups |
| CI/CD | GitHub Actions: every push to `main` deploys, runs migrations, and restarts the service |
| Tests | pytest (in memory database, Claude calls mocked), Vitest + Testing Library |

## How it's organized

```
backend/
  routers/     thin HTTP layer: validate input, call a service, return a response
  services/    all business logic; knows nothing about HTTP, so tests and n8n can reuse it
  models/      SQLAlchemy tables
  schemas/     Pydantic request and response shapes
  templates/   the locked resume template (HTML + CSS)
  alembic/     database migrations
  tests/
frontend/src/
  components/  applications, resume builder, auth, layout, shared UI
  lib/         typed API wrappers (api.ts) and types mirrored from the backend
deploy/        Caddyfile, systemd unit, backup script
docs/          design system, decision log, deploy runbook
```

The reasoning behind most choices is written down in [docs/decisions.md](docs/decisions.md).

## Running it locally

You'll need Python 3.13, [uv](https://docs.astral.sh/uv/), Node, and PostgreSQL. WeasyPrint also needs its system libraries (on macOS: `brew install weasyprint`, or see the [WeasyPrint install docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)).

**Backend**

```bash
cd backend
uv sync
# create backend/.env first, see below
uv run alembic upgrade head
uv run python scripts/seed_user.py   # create a login (there is no signup page)
uv run uvicorn main:app --reload     # http://localhost:8000, API docs at /docs
```

`backend/.env` needs:

```
ANTHROPIC_API_KEY=...
JWT_SECRET=...
DATABASE_URL=postgresql+psycopg://localhost/job_tracker
N8N_SERVICE_TOKEN=...   # optional, webhooks reject every call without it
```

**Frontend**

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api to the backend
```

**Tests**

```bash
cd backend && uv run pytest
cd frontend && npm test
```

Deployment steps are in [docs/deploy.md](docs/deploy.md).

## Author

Lethanial Leveille, Computer Engineering at the University of Florida. [GitHub](https://github.com/Lethanial-Leveille)
