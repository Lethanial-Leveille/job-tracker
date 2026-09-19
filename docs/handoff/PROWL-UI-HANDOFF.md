# Prowl UI handoff — v3

Everything needed to reproduce the v3 design pass in `frontend/`. Written for Claude Code working in the real repo.

Reference mock: `Prowl Redesign v3.dc.html` (four tabs: Applications, Detail, iPad & iPhone, Handoff notes).

Binding authority is `docs/design.md`. Where this document and that document disagree, that document wins.

---

## 0. The five rules everything else follows from

1. **Drama in the frame, calm in the data.** The geometric wash and glow live in the sidebar, top bar and empty space. Behind table rows: flat `#0A0810`. Nothing patterned behind text.
2. **Purple costs something.** It appears on exactly four things — the New application button, the active nav item, focus rings and links, and `offer`. Nowhere else. One purple dot in 64 rows is the point.
3. **No second accent.** No red, no amber, no green. Urgency is carried by *brightness*, not hue.
4. **A deadline you already met is noise.** Post-submit rows retire the deadline and count silence instead. Section 4.
5. **Density is the product.** 38px rows, 13px base, mono numerals. 64 applications should fit in two screens, not five.

---

## 1. Tokens

Tailwind v4, so these go in the `@theme` block in the global stylesheet. Names are suggestions; the values are not.

```css
@theme {
  /* Surfaces — near-black with a purple undertone */
  --color-base:        #0A0810;  /* page */
  --color-surface:     #0C0912;  /* cards, panels, table container */
  --color-surface-alt: #09070D;  /* stats strip, inset bands */
  --color-hover:       #120E1A;  /* row + control hover */
  --color-raised:      #150F20;  /* active nav, pressed segment */
  --color-overlay:     #100C16;  /* command palette, modals */
  --color-chrome:      #07050A;  /* app frame edge */

  /* Borders, lightest to heaviest */
  --color-line-row:    #131019;  /* between table rows */
  --color-line:        #17121F;  /* structural hairline */
  --color-line-frame:  #1A1522;  /* card + panel frames */
  --color-line-ctrl:   #241D31;  /* inputs, buttons, segmented */
  --color-line-accent: #2A2040;  /* purple-adjacent frame */

  /* Ink */
  --color-ink:         #F3F1F7;  /* headings, org names, urgent dates */
  --color-ink-body:    #D6D2E0;  /* body copy */
  --color-ink-2:       #A29BB0;  /* secondary */
  --color-ink-3:       #8B84A0;  /* tertiary, role cells */
  --color-ink-label:   #5C5570;  /* uppercase labels */
  --color-ink-spent:   #443E56;  /* retired values, hints */
  --color-ink-ghost:   #3A3448;  /* em dashes, disabled */

  /* Accent — the whole budget */
  --color-accent:      #7C4DF0;  /* button fill */
  --color-accent-edge: #8B5CF6;  /* button border, offer dot */
  --color-accent-text: #A78BFA;  /* links, "Suggested" label */
  --color-accent-soft: #C4B5FD;  /* offer status text, link hover */

  /* Status ink — greyscale on purpose */
  --color-stage-live:  #CFC9DC;  /* assessment, phone_screen, technical_interview */
  --color-stage-ring:  #EDEAF4;  /* their dot ring, and 21d+ silence */
  --color-stage-sent:  #6E6880;  /* applied */
  --color-stage-early: #2E2740;  /* discovered dot */

  --font-sans: 'Instrument Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}
```

Fonts: Instrument Sans 400–700 and JetBrains Mono 400–600, both from Google Fonts. Set `font-variant-numeric: tabular-nums` on `body` — it is what makes the date column align.

Glow (only on focus, hover, active, and the offer dot):

```css
--shadow-accent:      0 0 22px -10px rgb(139 92 246 / 0.95);  /* primary button */
--shadow-nav-active:  0 0 20px -9px rgb(139 92 246 / 0.55);   /* active nav item */
--shadow-offer-dot:   0 0 11px -1px rgb(139 92 246 / 0.95);   /* offer dot only */
--shadow-overlay:     0 26px 80px rgb(0 0 0 / 0.75), 0 0 60px -30px rgb(139 92 246 / 0.7);
```

Radii: **6px** structural frames (cards, panels, table container). **7–10px** interactive (buttons, tabs, inputs, toggles, palette). Nothing above 12px.

Motion: 120–160ms `ease-out`, hover and press only. No entrance animation on data. Respect `prefers-reduced-motion`.

Focus: `outline: 2px solid var(--color-accent-edge); outline-offset: 1px` on every row, tab, toggle and input. Required, not optional.

---

## 2. The background wash

Abstract geometric-organic, felt not seen. Two radial gradients per surface, 3–7% alpha, never behind rows.

```css
/* sidebar */
background-image:
  radial-gradient(120% 70% at 8% 0%,  rgb(139 92 246 / 0.07), transparent 58%),
  radial-gradient(90% 50% at 95% 100%, rgb(139 92 246 / 0.035), transparent 70%);

/* main top bar */
background-image: radial-gradient(70% 200% at 62% 0%, rgb(139 92 246 / 0.055), transparent 62%);

/* detail page */
background-image: radial-gradient(50% 40% at 80% 0%, rgb(139 92 246 / 0.045), transparent 60%);
```

If you have an SVG line texture already, keep it — cap it at 5% opacity and confine it to these same regions.

---

## 3. Applications list

### 3.1 Layout

```
┌ sidebar 210px ┬ main ─────────────────────────────────────┐
│ brand 23px    │ toolbar            48px  sticky           │
│ nav (2 items) │ stats strip        ~58px                  │
│ Views (3)     │ filter row         ~45px                  │
│               │ column header      29px  sticky top:92px  │
│ user card     │ rows               38px each              │
└───────────────┴ keyboard footer                           ┘
```

Sidebar is exactly two nav items — Applications and Resume — per the `Sidebar.tsx` comment. **Views** is a new third block; see 3.6.

### 3.2 The grid token

One definition in `components/applications/grid.ts` feeding both the header and every row. Do not let them drift.

```ts
const GRID_COLS =
  "md:grid-cols-[14px_minmax(120px,2fr)_minmax(100px,1.4fr)_minmax(96px,140px)_128px_46px]";

export const ROW_GRID    = `flex flex-col gap-1.5 md:grid ${GRID_COLS} md:items-center md:gap-x-[11px]`;
export const HEADER_GRID = `hidden md:grid ${GRID_COLS} md:items-center md:gap-x-[11px]`;
```

Columns: **status dot (14px) | Organization | Role | Status | Deadline / Sent | Actions (46px)**.

Minimum width is ~596px + 210px sidebar, so it fits any laptop without a horizontal scroll container. **Do not wrap the table in `overflow-x`** — any non-visible overflow on an ancestor breaks `position: sticky` on the column header.

Row height 38px, `border-bottom: 1px solid var(--color-line-row)`, hover `--color-hover`. Offer rows get `background: rgb(139 92 246 / 0.055)`.

### 3.3 Status column

The status pill is deleted. A repeated filled badge on 41 consecutive rows carries no information.

Replace with a **6px dot + a plain word**:

| status | dot fill | dot ring | label ink | weight |
|---|---|---|---|---|
| `discovered` | `#2E2740` | `#443E56` | `--color-ink-2` | 400 |
| `applied` | `#6E6880` | `#8B84A0` | `--color-ink-2` | 400 |
| `assessment` | `#CFC9DC` | `#EDEAF4` | `--color-ink` | 500 |
| `phone_screen` | `#CFC9DC` | `#EDEAF4` | `--color-ink` | 500 |
| `technical_interview` | `#CFC9DC` | `#EDEAF4` | `--color-ink` | 500 |
| `offer` | `#8B5CF6` + `--shadow-offer-dot` | `#A78BFA` | `--color-accent-soft` | 600 |
| `rejected` / `ghosted` / `missed_deadline` | `transparent` | `#2E2740` | `--color-ink-label` | 400 |

Closed rows also dim the org name to `--color-ink-label` and the role to `--color-ink-spent`. Present, visually silent.

Labels: `Discovered · Applied · Assessment · Phone screen · Tech interview · Offer · Rejected`.

The inline optimistic status edit stays exactly as it is — clicking the dot/label opens `StatusSelect`, the change is optimistic and rolls back on failure. That interaction is good; only its skin changes.

### 3.4 Column header

29px tall, `sticky top-[92px]` (44px app chrome + 48px toolbar — adjust if your chrome differs), `bg-base`, `z-40`, 10px uppercase `0.12em` in `--color-ink-spent`. The active sort column is `--color-ink-3` with a `▲`.

### 3.5 Grouping

`grouped` stays a boolean and still groups by organization. When on:

- Company header row, 27px, `bg-surface`, company name in 10.5px uppercase `--color-ink-2`, count in mono.
- Child rows indent 4px and get a 1px × 15px `#2A2237` tick before the label.
- **Child column 1 shows the posting title; column 2 shows the normalized `role_family`.** Never the same string twice — that is the FAB2 case ("Infrastructure and Site Reliability Intern" / "Other").

When off, rows are grouped by urgency instead — see 4.2.

### 3.6 Saved views (new, frontend-only)

A third sidebar block titled `VIEWS`, three entries, each a client-side predicate over data you already fetch. No schema change, no endpoint.

| view | predicate |
|---|---|
| Closing in 4 days | `isPreSubmit(status) && daysUntil(deadline) <= 4` |
| In process | `status ∈ {assessment, phone_screen, technical_interview, offer}` |
| Quiet 12+ days | `!isPreSubmit(status) && !isClosed(status) && daysSince(appliedAt) >= 12` |

Selected view = `--color-raised` background, `--color-ink` text. Clicking the active one clears it. Dots are `#EDEAF4`, `#8B5CF6` (with glow), `#5C5570` respectively — the In-process dot is purple because that set contains `offer`.

### 3.7 Stats strip

58px band, `--color-surface-alt`, four label/value pairs in mono 16px, then a 272px stacked bar right-aligned.

`Tracked 64 · Applied 41 (64%) · In process 3 · Closing ≤7d 6 (unapplied)`

Bar segments, 5px tall, 1px gaps: Discovered `#3D3750` · Applied `#8B84A0` · Offer `#8B5CF6` with glow · Closed `#1E1828`. Legend beneath in 10px `--color-ink-label`, with the Offer legend in `--color-accent-text`.

### 3.8 Toolbar

48px, one line: title (14px/600) · count (11px mono) · search (286px, 29px tall, with a `⌘K` chip) · spacer · **New application** (29px, `--color-accent` fill, `--color-accent-edge` border, `--shadow-accent`, trailing `N` hint at 65% opacity).

### 3.9 Filter row

Three real tabs — `All / Not applied / Applied` — matching `StatusFilter` exactly. Segmented control: 2px padding, `--color-surface` track, `--color-line` border, 8px radius; active segment `#1C1528` + `--color-ink`, inactive `--color-ink-3`. Count in 10px mono beside each label.

Right side: the group-by-company switch as an actual 22×12 toggle (knob 8px, `#A78BFA` when on, `#6E6880` when off), plus a plain-text sort caption in `--color-ink-label`.

### 3.10 Keyboard footer

11px mono, `--color-ink-spent`, top hairline: `↑↓ move · ⏎ open · E mark applied · ⇧S status · ⌘Z undo`, with `N shown of 64` right-aligned. Ship the footer only once the shortcuts actually work (section 7).

---

## 4. The deadline rule

The one genuinely new behaviour. Implement this before any cosmetic work — it changes what the list is *for*.

### 4.1 The rule

A posting deadline is only actionable while you have not applied. Once `status` leaves the pre-submit set, the column keeps its width and switches meaning.

| state | column shows | ink |
|---|---|---|
| pre-submit, ≤4 days | `Sep 12` + `in 3 days` | `--color-ink` / `#CFC9DC` |
| pre-submit, >4 days | `Sep 26` + `in 17 days` | `--color-ink-2` / `--color-ink-label` |
| post-submit | `Sent Sep 2` + `quiet 7d` | `--color-ink-3` / `--color-ink-label` |
| post-submit, ≥21d quiet | `Sent Aug 14` + `quiet 26d` | `--color-ink-3` / `#EDEAF4` |
| closed | `—` | `--color-ink-ghost` |

Brightness *is* the urgency signal. There is no red and no amber.

The original deadline is not destroyed — it moves to the detail page fact grid, greyed, labelled `Sep 5 · spent`.

### 4.2 Section order when not grouped by company

1. **Closing this week** — pre-submit, ≤4 days. Header ink `#EDEAF4`. Hint: "not applied yet — act on these first".
2. **Open, further out** — pre-submit, >4 days. Header ink `--color-ink-3`.
3. **In flight** — post-submit, not closed, sorted by descending silence. Header ink `--color-ink-2`. Hint: "deadline retired — counting silence instead".
4. **Closed** — rejected / ghosted / missed_deadline. Header ink `#4E4860`.

Empty sections are omitted entirely.

### 4.3 Code

`isPreSubmit(status)` already exists in `components/applications/statuses.ts`. Add its sibling and the derived timestamp:

```ts
// statuses.ts
export const CLOSED_STATUSES: ApplicationStatus[] =
  ["rejected", "ghosted", "declined", "missed_deadline"];

export function isClosed(status: ApplicationStatus): boolean {
  return CLOSED_STATUSES.includes(status);
}
```

```ts
// lib/format.ts
// No migration needed: the first `applied` entry in status history IS applied_at.
export function appliedAt(app: Application): string | null {
  const first = app.status_history
    ?.filter(h => h.to_status === "applied")
    .sort((a, b) => a.changed_at.localeCompare(b.changed_at))[0];
  return first?.changed_at ?? null;
}

export function daysSince(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}
```

`DeadlineCell.tsx` becomes a branch, not a date formatter:

```tsx
export function DeadlineCell({ app }: { app: Application }) {
  if (isClosed(app.status)) return <span className="text-ink-ghost font-mono">—</span>;

  if (!isPreSubmit(app.status)) {
    const sent = appliedAt(app);
    if (!sent) return <span className="text-ink-ghost font-mono">—</span>;
    const quiet = daysSince(sent);
    return (
      <span className="font-mono text-[12px] text-ink-3">
        Sent {fmtShort(sent)}{" "}
        <span className={quiet >= 21 ? "text-[10.5px] text-stage-ring" : "text-[10.5px] text-ink-label"}>
          quiet {quiet}d
        </span>
      </span>
    );
  }

  const days = daysUntil(app.deadline);
  const urgent = days !== null && days <= 4;
  return (
    <span className={`font-mono text-[12px] ${urgent ? "text-ink" : "text-ink-2"}`}>
      {fmtShort(app.deadline)}{" "}
      <span className={`text-[10.5px] ${urgent ? "text-stage-live" : "text-ink-label"}`}>
        {relative(app.deadline)}
      </span>
    </span>
  );
}
```

If `status_history` is not currently returned on the list endpoint, add `applied_at` as a computed read-only field on `ApplicationRead` rather than N+1 fetching. Still no migration.

Column header label becomes **`Deadline / Sent`**.

---

## 5. Application detail

Single layer, tabs, no slide-overs — as already decided. Two columns: content `minmax(0,1fr)` and a 292px right rail, 24px gap.

**Header.** 38px monogram tile (`#140F1D`, `--color-line-ctrl`, 6px) · org name 21px/600 `-0.02em` · req id chip in 11px mono · role + location line in `--color-ink-2`. Right: status control (dot + label + chevron, opens `StatusSelect`) and `↗ Posting`. Breadcrumb above, with `3 of 64` and `j`/`k` chips on the right.

**Suggestion banner.** Directly under the header when one is pending. `--color-line-accent` border, `#110C1B` fill, `0 0 30px -18px` purple glow, a `SUGGESTED` chip in `--color-accent-text`, the matched sender and date, then `Review` / `Dismiss`. It proposes; it never applies. This is `SuggestionsPanel.tsx` promoted from a side panel to the first thing you see.

**Tabs.** `Overview · Tailor resume (n) · Fit`. Active gets a 1.5px `--color-accent-edge` underline.

**Fact grid** replaces six full-width form inputs. Two columns, 1px `--color-line-frame` gutters, 6px outer radius, each cell an uppercase 10px label over a 13px value:

`Status` (stage · sent · quiet) · `Deadline` (`Sep 5 · spent`, greyed) · `Role family` · `Compensation` (mono) · `Locations` · `Grad date used` (`May 2028 · from posting` — surfacing the `gradHint` decision).

Editing happens in place on click, not in a permanently-open form.

**Requirements match** (`FitSection.tsx`): a header with `7 met · 2 partial · 1 missing` in mono, a 4px three-segment bar (`#CFC9DC` / `#5C5570` / `#251F33`), then a `✓ / ~ / ·` list with the cited evidence right-aligned in `--color-ink-label`.

**Right rail**, three cards:
1. **Status history** — `StatusTimeline.tsx`. 7px dots on a 1px `--color-line` spine, most recent first, each with `date · source` in mono (`manual`, `suggested from email`, `Handshake paste`). This is the honest replacement for a pipeline stepper: transitions are a vocabulary, not a sequence.
2. **Tailored resumes** — PDF chip, `v2 · sent`, date + page count, a `Diff` link, archived versions beneath.
3. **Source** — `Handshake → careers.mastercard.com`, req id, and the spent deadline for the record.

---

## 6. Responsive

### iPhone (< `md`)

Rows already stack into mini-cards; give the card real structure. 68px+ tall, 12px/16px padding, `--color-line` top border.

- Line 1: org 15px/600 (left) · date value 13px mono (right).
- Line 2: role 13.5px `--color-ink-3`.
- Line 3: status dot + label (left) · the date's sub-value — `in 3 days` / `quiet 7d` (right).

Header collapses to hamburger + title + a 36px square accent `+`. Search full width, 38px. The three filter tabs become a full-width segmented control, 30px segments. Swipe-left on a card reveals **Mark applied** — the phone equivalent of the `E` shortcut.

### iPad (portrait, `md`–`lg`)

Sidebar becomes a 62px icon rail: brand tile, an active 44×40 nav tile showing icon over count, a second nav icon, avatar pinned bottom. Labels return in landscape.

Table keeps every data column and drops **only** the 46px actions column; the whole 46px row is the tap target. Grid: `14px minmax(0,1.6fr) minmax(0,1.2fr) 140px 126px`, 12px gap. Toolbar 54px, controls 34px, search 220px.

Nothing below 44pt on either device.

---

## 7. Build order

**P0 — behaviour**
1. `isClosed`, `appliedAt`, `daysSince` in `statuses.ts` / `format.ts`.
2. `DeadlineCell.tsx` branch + `Deadline / Sent` header.
3. Urgency sectioning in `ApplicationsPage.tsx` when `grouped === false`.
4. Keyboard nav: `j/k`, `⏎`, `e`, `⇧S`, `x`, `⌘Z` over the existing optimistic mutation. Undo toast, never a confirm dialog. Ship the footer only after this lands.
5. Saved views as client-side predicates (3.6).

**P1 — surface**
6. Token block, fonts, `tabular-nums`, focus ring.
7. `StatusBadge.tsx` → dot + word (3.3). Delete the pill.
8. Grid token, 38px rows, hairlines, sticky header — with **no** `overflow-x` ancestor.
9. Toolbar, stats strip, filter row, background wash.
10. Detail page: fact grid, suggestion banner promotion, right rail.

**P2 — reach**
11. Responsive card and rail (section 6).
12. `⌘K` palette (search + the five commands in the mock).
13. Empty / skeleton / parse-failure / offline states.
14. Follow-up digest at 21 days quiet — proposes, never sends.

---

## 8. Regressions to avoid

- **`overflow-x` anywhere above the table.** Any non-visible overflow on an ancestor captures `position: sticky` and parks the column header mid-list. Fix width by trimming `minmax()` floors, never by adding a scroll container.
- **Header and row grids drifting apart.** They must read the same exported token.
- **Duplicating role text in grouped mode.** Column 1 is the posting title, column 2 is `role_family`.
- **Purple creeping past its four uses.** If a screen has purple in more than four places, pull it back.
- **Reintroducing red or amber for urgency.** Brightness only.
- **Advertising what does not exist.** No greyed-out "Soon" nav entries. Ship a view or leave it out.
- **Anything that auto-submits or silently changes state.** Suggestions propose. Duplicates warn. Everything is reviewed.
