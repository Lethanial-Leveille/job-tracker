# Vision: Job and Scholarship Tracker

This is the north star for the project. It is NOT the build spec. It describes where this is going so I don't lose the thread, but day to day work is guided by `docs/decisions.md` and by whatever the current version's scope is. When this doc and reality disagree, reality wins, and I update this doc.

Rule for myself: nothing in the "Someday" sections gets built until the version that owns it. If I find myself building a v5 feature during v1, I stop.

---

## What this is

A single user tracker for internship and scholarship applications. It is three things at once, in priority order:

1. A real tool I use through Fall 2026 application season and beyond. Fall 2026 I expect to apply to 30 to 50 internships plus 10 or more scholarships. Without a system I lose deadlines and submit weak applications. With one I triage smarter and reuse my own writing.
2. A flagship full stack portfolio project. Full stack, AI integration, production deployment, real world use. The interview story is strong because I actually use it.
3. A piece of my broader life OS. It exposes a REST API that n8n, Notion, and eventually Nova (M.I.L.E.S.) can all read from.

If it only ever becomes #1, a reliable tool I actually use, it succeeded. Everything else is upside.

---

## The one design idea that matters most

Separate content from format, everywhere.

The clearest example is resume tailoring: a master resume lives as structured YAML (the content), and a locked renderer turns YAML into a styled PDF (the format). Claude only ever rewrites the YAML content. It never touches the renderer. That means every tailored resume looks identical no matter how many I generate, and the AI can never break my formatting because it can't see it.

The same principle shows up all over: the database stores structured data, the UI renders it; Notion holds prose, the tracker holds metadata. Each tool does the job it is good at. Keep this principle even when the features change.

---

## Guardrails (these never change)

- The tracker never submits anything for me. It drafts. I review. I submit. Always.
- Resume bullets are never invented. The renderer can reorder, the tailoring step can rephrase, but no new claims, metrics, or technologies.
- Follow up emails are drafted, never auto sent.
- The tracker never holds my application login credentials. I never automate a Submit button.
- Single user, behind auth, on my own infra. My application data stays mine. No third party telemetry.

---

## Stack (the direction, not a v1 checklist)

- Backend: Python, FastAPI
- Database: SQLite for local and early versions, Postgres later when I actually need concurrency or pgvector
- Frontend: React, TypeScript, Vite, Tailwind, dark theme
- AI: Claude API. Confirm the current model string at https://docs.claude.com before hardcoding. Use the cheaper capable model for parsing and routine work, the top model only for resume tailoring and essay drafts.
- Deployment: DigitalOcean droplet, Student Pack covers cost
- Domain: track.lethanial.com
- Automation: n8n on the Raspberry Pi calls the tracker's API. No Celery unless I outgrow n8n.
- Storage: DigitalOcean Spaces for generated PDFs

Why this stack: I already know Python and React. FastAPI gives clean OpenAPI docs that n8n consumes directly. Postgres is worth knowing for interviews. Nothing exotic.

---

## Now vs Someday

This is the important part. The line between what I build first and what I defer.

### NOW (v1): the smallest real tool

One table. Manual everything. Running locally.

- One `applications` table: internship and scholarship only
- Create, read, update, list an application by hand
- Status field with the full pipeline enum, no transition logic yet
- No JD parsing yet, no AI, no deployment
- Goal: a working CRUD loop I can add a real scholarship to this week

Ship it plain. The point is a working foundation, not a feature.

### SOON (v2 to v3): the parts that make it feel smart

- v2: paste a URL, Claude parses the job or scholarship into structured fields. This is the "magic" feature and it comes second, after CRUD is solid.
- v2: resume tailoring. YAML master, locked renderer, tailoring endpoint. This is where `resume_versions` gets built, not before.
- v3: deploy to DigitalOcean. JWT auth. Reachable at track.lethanial.com.
- v3: Notion mirror for essay and longform drafts. Essays live in Notion because it is a better writing environment than anything I would build.

### LATER (v4+): the automation and life OS layer

Only after the tool is deployed and I am using it for real.

- n8n Gmail watcher: classifies application emails, updates status via webhook. This is when `timeline_events` gets built.
- n8n Calendar watcher: interview events flip status, trigger prep docs.
- n8n deadline and follow up managers: morning deadline nudges, Monday follow up drafts.
- Weekly stats endpoint feeding my Sunday review.
- Discovery scrapers: company career pages and scholarship boards, auto inserted as "discovered."
- Browser extension: detect a job posting, scrape it, POST to the API to create a draft application. Depends on v2 parsing and v3 deployment. Its own mini-project.

### SOMEDAY (maybe never): the ambitious tail

Genuinely optional. Do not let these tempt me early.

- Essay similarity search. Only worth pgvector once I have 30 or more essays and actually feel the pain of finding them. Until then a folder of files is fine.
- Analytics dashboard: response rate, interview rate, time in pipeline.
- MCP server so Nova answers pipeline questions by voice.
- Open source release with a blog post and a public master YAML template.

---

## Resume tailoring architecture (reference for when v2 arrives)

The design is settled even though the build is deferred. Capturing it so I don't relitigate later.

```
master_resume.yaml   ← single source of truth, structured data
      │
      ▼
[ Claude tailoring ] ← reads master YAML + job description, rewrites and reorders bullets, returns new YAML
      │
      ▼
tailored_resume.yaml ← same schema, optimized content
      │
      ▼
[ Renderer ]         ← locked code, formats everything: fonts, colors, margins, tab stops
      │
      ▼
tailored_resume.pdf  ← styled, identical look across every application
```

The renderer is locked code Claude never sees. Content and format never mix. One master file means updating a bullet once propagates to every future tailored resume.

Tailoring prompt rules, when I build it: same schema in and out, reorder by relevance, keep the strongest four bullets per entry, rephrase only using facts already present, never invent anything, output only YAML.

---

## The status pipeline (the enum to start from)

Use these values as the starting enum. No transition validation in v1, just the vocabulary.

discovered, shortlisted, drafting, ready, applied, applied_confirmed, recruiter_engaged, phone_screen, technical_interview, onsite, offer, accepted, declined, rejected, ghosted, missed_deadline

An internship walks toward offer and accepted. A scholarship walks toward offer (award) and skips the interview stages. Both share one enum so the pipeline is one component, not two.

Note on deadline semantics: deadline is meaningful for scholarships (hard cutoffs) and mostly not for internships (rolling, recency driven). For jobs the real urgency signal is staleness, days since discovered while unapplied, derivable from created_at. Consider surfacing that in a later version.

---

## Scholarships to seed once v1 exists

Add these the day the tool works. Ordered by priority.

Top priority, timing sensitive or large: SMART Scholarship (DoD), Ron Brown Scholar Program, Gates Scholarship, Apple Scholars, Generation Google Scholarship, Microsoft Tuition Scholarship.

High priority, recurring, strong fit: NSBE chapter and national, NACME, UNCF STEM, SHPE, Google Lime, Amazon Future Engineer, Intel, Development Fund for Black Students in Science and Technology, ColorStack board.

UF specific: Office of Student Financial Affairs, Herbert Wertheim College of Engineering, CISE department, cultural org scholarships.

Later, post junior year: NSF REU, UF CURBS, Goldwater, GEM Fellowship.

---

## The interview story this becomes

The target, roughly, for a recruiter screen in late 2026:

I built a job and scholarship tracker in Python and React, deployed to DigitalOcean. It uses the Claude API to parse postings and tailor my resume per application, separating content as YAML from format as locked rendering code so every output keeps the same style. n8n on a Raspberry Pi watches my Gmail and calendar to auto update status and scrapes career pages for new postings. I used it through this whole application cycle, including this one.

That paragraph carries full stack engineering, AI integration, production deployment, and real product thinking. It only works if the tool is real and used, which is why v1 minimalism matters more than any single feature.

---

## Open questions I answered (so I stop reopening them)

- SQLite or Postgres for v1? SQLite. Postgres only when I deploy for real and need concurrency or pgvector.
- Pgvector for essay similarity? No, not for a long time. Not worth it under ~30 essays.
- Weekend 1 scope? CRUD loop first, JD parsing second. One unknown at a time.
- Biggest regret risk in October? Building too much scaffolding and never shipping a usable tool. The fix is ruthless v1 minimalism.

---

*This is a living north star. Update it when direction changes. Build state lives in git and `docs/decisions.md`, not here.*