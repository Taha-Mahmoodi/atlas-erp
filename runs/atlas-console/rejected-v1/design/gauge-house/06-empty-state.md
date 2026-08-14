# gauge-house: Surface 6 of 7 — Empty state (filtered)

Fixes the finding in `SCOUT.md` §"absence sweep": the live app renders filtered-empty
identically to true-empty (`list-inventory-filtered-empty.png` — a raw `<select>` reading
"Non-stocked" over a table that just says "No items yet.", no way to tell filtered from
truly-empty, no clear-filters affordance). This comp replaces the native `<select>` with a
removable filter chip, adds an explicit "Clear filters" action next to it, and gives the
empty body its own copy distinct from true-empty's.

Canvas: fixed 1440×900 desktop viewport, full chrome (left rail + top bar + content), matching
the dimensions of the current-state screenshots in `shots/current/`.

## Composition anchor: `centered-statement`
## Background mode: `flat-surface`

One line: the items-list sibling is a dense working table — many rows, eye moving across
columns. This surface has zero rows by design, so the one thing worth looking at is the
certificate-note block sitting on-axis inside an otherwise-empty ruled table frame; rail, top
bar, header and filter row all go quiet around it. `flat-surface` because a "quieter surface"
earns quiet more than it earns a texture layer — no grid paper, no gradient, one solid
substrate throughout, consistent with the rest of the chrome.

---

## Layout move — exact numbers

**Chrome (unchanged from items-list sibling, held constant across the set):**

| Region | Box (x, y, w, h) | Notes |
|---|---|---|
| Left rail | 0, 0, 224, 900 | substrate fill, 1px hairline right border |
| Top bar | 224, 0, 1216, 64 | substrate fill, 1px hairline bottom border |
| Content padding | 40px left/right from content origin (x=224) → content spans x 264–1400 | |

**Left rail nav:** 13 rows × 40px, starting y=72 (Home, Finance, **Inventory** [active],
Procurement, Sales, Manufacturing, Quality, Maintenance, HR, Projects, CRM, Reporting, Admin).
Active row (Inventory): full-bleed accent-tint fill, 3px solid accent-ink left flag bar
(x=0–3), label in accent-ink. Inactive rows: label in secondary-text, no fill. Wordmark "Atlas
ERP" at (24, 24).

**Top bar:** "owner@acme.test" at (264, y vertically centered in 64px bar), secondary-text.
"Sign out" right-aligned ending at x=1416, accent-ink, link-style (underline on hover/focus).

**Header row:** y=96–124 (28px tall). "Items" screen-title at (264, 96). "New item" primary
button, 100×36px, at (1300, 88)–(1400, 124) — accent-emphasis fill, white label.

**Filter row — the fix, part 1:** y=148–176 (28px tall), starting x=264.
- **Filter chip**, x=264–412 (148px wide), 28px tall, 2px corner radius, 1px hairline border,
  accent-tint fill, 10px horizontal padding: `CATEGORY` (section-eyebrow, secondary-text) +
  `Non-stocked` (mono-identifier, accent-ink) + 1px vertical hairline divider + 18×18px `×`
  remove target (accent-ink, `aria-label="Remove Category filter"`).
- **"Clear filters"** text button, 12px gap after the chip at x=424, vertically centered in the
  row, accent-ink, 14px/500, underline on hover/focus. This is the literal fix: a filter chip
  the current build renders as an unlabeled native `<select>`, plus a named clear action next
  to it — neither exists today.
- Not reused from the status-chip vocabulary (`Draft`/`Pending`/`Posted`/`Error`/`Closed`,
  shape+label+glyph): a filter isn't a document status, and borrowing one of those five colors
  here would falsely imply the zero-row result *is* a status. Same chip grammar (hairline
  border, shape+label, no color-only signal), new semantic role.

**Table frame:** x=264–1400, y=196–560.
- Header row, y=196–228 (32px): `ITEM #` (264–360) `NAME` (376–760) `TYPE` (776–968)
  `COSTING` (984–1176) `STATUS` (1192–1400), section-eyebrow role, 1px hairline bottom border.
- **Empty body**, y=228–560 (332px), left/right/bottom hairline borders closing the frame —
  a ruled, empty table (the frame still stands with nothing in it) reads as the direction's own
  "flat, authoritative technical drawing," not a missing feature.
  - Content block centered in the 332px region (visual center ≈ x=832, y=394), max-width 420px.
  - Certificate-plate glyph: 48×48px square, 1.5px stroke, secondary-text (not the hairline
    token — see "couldn't satisfy" below), centered.
  - 16px gap → headline, 8px gap → supporting line.

## Content direction — the fix, part 2

Two-line certificate note, distinct from true-empty's "No certificate on file. Log the first
item to open one.":

- **Headline** (screen-title, 20/600, primary-text, centered): **"No certificate on file for
  this filter."**
- **Supporting line** (body/data, 14/450, centered): connective words in secondary-text, the
  two actions rendered inline as accent-ink 14/500 underlined links, not a second button pair
  (keeps the body quiet — the named "Clear filters" action already lives in the filter row):
  **"Clear it, or log the first item to open one."** — "Clear it" links to the same clear-filter
  action as the filter-row button; "log the first item" routes to the new-item form.

---

## Type table

| Role | Face | Size | Weight | Line-height | Used here for |
|---|---|---|---|---|---|
| screen title | Inter Variable | 20px | 600 | 28px (declared here — not given upstream) | "Items", empty-state headline |
| section-eyebrow | Inter Variable | 12px | 600, uppercase, +0.04em | 16px (declared here) | table column headers, chip's "CATEGORY" label |
| body/data | Inter Variable | 14px | 450 (tabular-nums where numeric; n/a on prose here) | 20px (declared here) | nav labels, top-bar email, supporting line's connective words |
| meta | Inter Variable | 12px | 450 | 16px (declared here) | *not used on this surface — no metadata row present with zero items* |
| mono-identifier | IBM Plex Mono Variable | 13px | 500 | 18px (declared here) | chip's filter value "Non-stocked" |

**One declared deviation, flagged rather than silent:** button labels ("New item", "Clear
filters", the inline "Clear it" / "log the first item" links) use the **body/data role at 600
weight** — same 14px size, a 600-weight variant, not a new scale step. No button-label role
exists in the dispatch's type table or in `DIRECTION.md`'s five roles; reusing body/data with a
weight bump was the smaller move than inventing a sixth size.

Line-heights are not stated anywhere I read (dispatch, `DIRECTION.md`) — the five values above
are my own declaration at typical ratios (1.33–1.43×), not upstream-given. Flagging so a
reviewer knows to check them against whatever the type system settles on elsewhere.

---

## Paired colors, with ratios

| Foreground | Background | Ratio | Source | Used for |
|---|---|---|---|---|
| primary text `oklch(0.20 0.01 58)` | substrate `oklch(0.985 0.003 58)` | **17.35:1** | computed, not rendered | "Items", empty-state headline |
| secondary text `oklch(0.45 0.012 58)` | substrate `oklch(0.985 0.003 58)` | **7.14:1** | computed, not rendered | nav labels, top-bar email, connective prose |
| accent-ink `oklch(0.42 0.09 58)` | substrate `oklch(0.985 0.003 58)` | **8.34:1** | computed, not rendered (dispatch states ≈8.71:1 for the same pair — both clear 4.5:1 with room; treating the ~0.4 gap as a rounding/method difference between OKLCH→sRGB conversions, not a discrepancy worth chasing) | "Clear filters", "Sign out", inline action links |
| white | accent-emphasis `oklch(0.55 0.13 58)` | **5.06:1** | computed, not rendered — matches dispatch's stated ≈5.06:1 exactly | "New item" button label |
| accent-ink `oklch(0.42 0.09 58)` | accent-tint `oklch(0.94 0.03 58)` | **7.26:1** | computed, not rendered — matches `direction-draft.md`'s stated ≈7.27:1 for this pair | chip's "Non-stocked" value, chip's `×` remove glyph, active nav label + flag bar |
| secondary text `oklch(0.45 0.012 58)` | accent-tint `oklch(0.94 0.03 58)` | **6.23:1** | computed, not rendered | chip's "CATEGORY" eyebrow |
| hairline `oklch(0.88 0.008 58)` | substrate `oklch(0.985 0.003 58)` | **1.38:1** | computed, not rendered | table frame rules, chip border, top-bar/rail dividers |

Every text pair above clears 4.5:1 (smallest is 5.06:1) with margin.

---

## Embarrassment-gate self-check

- Palette hexes/OKLCH values on the board: yes — every color used above traces to the dispatch
  or `DIRECTION.md`'s Concept A build-out verbatim, none invented.
- Body-size type legible, contrast plausible at 4.5:1: yes, checked above, smallest pair is
  5.06:1.
- Four bands / equivalent chrome: N/A per the surface table — this is a tool-shaped desktop
  screen, not mobile; the desktop equivalent (rail + top bar reserved, never bled under) is
  held per the layout table above.
- Collision readable: yes — data-brutalist structure (hairline-ruled table frame, held open and
  ruled even at zero rows, tabular/mono identifiers) carries the surface; blueprint reads in
  the flat authoritative substrate and the certificate-plate motif standing in for a stamped
  calibration mark, applied to the *empty-state itself* rather than decorating all forty rows —
  consistent with the concept's own "style-under-density" note in `DIRECTION.md`.
- Differs from siblings: dense-grid sibling (items-list) is full of rows and eye-across-columns;
  this is `centered-statement` on an intentionally empty frame — the quietest surface in the set,
  as the dispatch asked for.
- No garbled text, no invented logo, no hollow superlative: copy is the two real sentences
  given/derived, no lorem, no fabricated numbers (zero rows is the actual data state, not a
  claim).
- Anchor/background tokens describe what's actually there: yes, checked against the definitions
  above before logging.

Would a designer put their name on this: yes — it fixes the actual finding (filtered vs. true
empty were indistinguishable, no clear-filters path existed) with the direction's own visual
grammar, not a generic empty-state pattern pasted in.

---

**Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/gauge-house/06-empty-state.md`
**Composition anchor:** `centered-statement`
**Background mode:** `flat-surface`

**One line:** a certificate-note block held on-axis inside a ruled-but-empty table frame,
against a rail/top-bar/filter-row that stay quiet — the dense items-list sibling earns its
`dense-grid` anchor from forty real rows; this surface earns `centered-statement` from having
none, and says so.

**Couldn't fully satisfy:**
- The hairline border token, computed fresh, is **1.38:1** against substrate — visibly fainter
  than the "hairline-ruled tables" identity implies for a direction whose entire structural
  premise is ruled lines. Not mine to change (the OKLCH values are given, upstream), but worth
  a visual check at build time on the actual table frame — if the ruling doesn't read, the
  empty-body's "ruled frame with nothing in it" move (this comp's main legibility bet) is the
  first place it will show.
- No button-label or line-height role exists upstream; both declared here (see type table) and
  flagged rather than silently assumed, since a sixth surface picking a different value would
  fragment the set.