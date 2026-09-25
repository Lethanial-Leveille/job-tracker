# Prowl → MILES integration

The contract MILES calls. Written for whoever builds `prowl_tools.py` on the Pi.

Prowl is a single user job application tracker. MILES reads its pipeline so Nova
can answer questions about the job search and raise things that were forgotten.

## Connection

```
Base    https://tracker.lethanial.com/api
Header  X-Miles-Token: <PROWL_TOKEN from miles/.env>
```

Caddy strips the `/api` prefix, so `/api/integrations/miles/summary` reaches
FastAPI as `/integrations/miles/summary`. Build URLs against the base above and
do not strip it yourself.

The token is Prowl's third auth path, separate from the n8n service token and
from the login JWT. It is on its own header on purpose: `Authorization: Bearer`
is where a user's login token goes, and mixing them means something eventually
has to guess which kind of credential it is holding.

### Errors

| Code | Meaning | Action |
| --- | --- | --- |
| 401 | Token missing or wrong | Config problem on the Pi. Do not retry. |
| 404 | No such application or discovery | The id is stale. Re-read the list. |
| 500 | `OWNER_EMAIL` unset on the server | Config problem on the droplet. Do not retry. |

None of these are transient. A failure means something is misconfigured, so
surface it rather than retrying in a loop.

## Endpoints

### `GET /integrations/miles/applications`

Query: `status=<enum>` (optional), `include_closed=true|false` (default false).

Closed rows (`rejected`, `ghosted`, `declined`, `accepted`, `missed_deadline`)
are excluded by default. A search that has been running a while is mostly
rejections, and including them makes every count sound worse than it is.

### `GET /integrations/miles/applications/{id}`

Everything from the list row plus `location`, `salary`, `summary`,
`key_requirements`, `notes`, and three requirement counts.

There is deliberately **no posting text**. If someone asks what a job requires,
`key_requirements` is the answer.

### `GET /integrations/miles/discovered`

The discovery inbox, best fit first. Rows with no `fit_score` sort last rather
than as zero: unscored means the posting could not be read, which is not the
same as a bad match. Never speak a null score as a zero.

`possible_duplicate_of` being non-empty means Prowl thinks this may already be
in the pipeline. Say so before accepting it.

### `POST /integrations/miles/discovered/{job_id}/accept`

**The only write.** Files a discovered job into the pipeline at status
`discovered`. It sends nothing, submits nothing, and spends no network call.

Takes no body. Returns the created application.

Confirm with the user before calling this, by name, every time. It is driven by
speech and speech gets misheard. There is deliberately no bulk accept and no
"accept the best one": the caller names exactly one id.

### `GET /integrations/miles/summary`

Query: `deadline_days=<1..90>` (default 7).

The important one. Built for a morning brief rather than for arbitrary
questions, because the value of a tracker attached to an assistant is the thing
that was forgotten, not the thing someone remembered to ask.

```
active_count          live applications
counts_by_status      {status: count}, all rows including closed
upcoming_deadlines    deadline within the window, soonest first, max 5
overdue               deadline passed AND never applied, most recent first, max 5
stale                 applied, untouched 14+ days, longest silence first, max 5
pending_suggestions   status changes awaiting review, max 5
discovered_waiting    count of jobs in the discovery inbox
```

`overdue` and `upcoming_deadlines` are separate on purpose. One is "this is
coming up", the other is "this got away from you". They are different sentences.

## Field semantics

**Every quantity carries its unit in its name.** `days_until_deadline`, not a
bare date to subtract. This exists because of a real bug in this codebase's
history: an Oura contributor score out of 100 was read as 100 minutes and spoken
as a sleep duration. Do not reintroduce that by doing date math on the raw
fields when a day count is already provided.

- `days_until_deadline` — negative means the deadline has passed
- `days_since_applied` — **null means never applied**, not applied today
- `days_since_last_change` — how long the row has sat at its current status
- `fit_score` — 0 to 100, **null means unknown**, not a bad match
- `needs_a_screen` on a suggestion — matched nothing, or matched several. Do not
  present it as actionable by voice

## Rules for the MILES side

**Do not recount anything.** Every count, filter and day difference is already
computed in Python on the server. Re-deriving them from the rows is how a
confident wrong number gets spoken aloud, and a spoken wrong number sounds
exactly as certain as a right one.

**`min_tier="hokage"` on every tool.** A job search is private. This should be
answerable to Lethanial and to nobody else in the room.

**Keep responses small.** Everything returned here goes into a voice turn's
context and adds latency.

## Deliberately not available

Resume content, resume tailoring, creating an application, sending anything,
and the raw text of any posting. Tailoring is an expensive call producing a
document that must be read carefully before use, and Prowl's standing rule is
that it proposes while a human submits. Putting a microphone in front of it
does not change that.
