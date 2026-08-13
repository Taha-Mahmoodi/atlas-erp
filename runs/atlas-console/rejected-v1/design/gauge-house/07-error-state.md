# gauge-house: Surface 7 of 7 — Error state

**Concept:** gauge-house — data-brutalist (structure) × blueprint (surface). A technical
drawing is flat and authoritative; stamping each number with a calibration certificate
(measured value, tolerance, checked-by, date) makes precision auditable, not just readable.

**Surface:** 07-error-state — bad/malformed item-ID lookup. Replaces the live bug: editing
`ITM-4471` (a deleted or mistyped ID) currently returns a swallowed 422 and renders an empty
"Edit item" form indistinguishable from a blank draft. This comp is the real designed
Error state per TOOLS.md §4/§9: name what happened, confirm nothing was lost, give a next
action — in operator vocabulary, no "Something went wrong."

**Canvas:** 1440×900, fixed viewport, full chrome (persistent sidebar + topbar), platform
mode N/A (desktop-only, no iOS/Android component rules apply). No primary data grid on this
surface — the only tabular element is the 5-row certificate-fields table below, shown in
full, which is why "real row counts" here means 5 of 5, not a paginated list.

---

## Composition anchor: `centered-statement`

One stamped certificate card, on both axes of the content field. Sidebar and topbar chrome
render in full and stay subordinate — no competing focal point.

## Background mode: `textured-surface`

A low-contrast blueprint grid — hairline lines, no image, no gradient — sits under the card
across the whole content field. It is the surface half of the collision; the certificate
card is the structure half.

---

## Layout move (exact numbers)

**Chrome (unchanged position from the live app, restyled to this palette):**

- Sidebar: `x 0–224, y 0–900`. Substrate fill, 1px hairline border on the right edge (`x=224`).
  Wordmark "Atlas ERP" at `x=24, y=24`, title role. Nav list starts `y=76`, 13 items × 40px
  row height (Home, Finance, Inventory[active], Procurement, Sales, Manufacturing, Quality,
  Maintenance, HR, Projects, CRM, Reporting, Admin) → ends `y=596`. Active row ("Inventory",
  3rd item): `y 156–196`, 3px accent-ink bar at `x 0–3`, row fill = accent-ink mixed 8% into
  substrate (chrome-state tint, not a listed palette token — flagged below).
- Topbar: `x 224–1440, y 0–56`, 1px hairline bottom border. **Added** vs. the live screen:
  a breadcrumb, which the live bug-state has none of. Left, `x=256`, vertically centered:
  "Inventory / Items / `ITM-4471`" (parent segments secondary text, `ITM-4471` in mono,
  primary text — the fix surfaces the exact bad ID instead of hiding it). Right cluster
  ending `x=1416`: "owner@acme.test" (secondary text) · 1px hairline divider, 16px height ·
  "Sign out" (accent-ink) — moved here from the topbar's left slot to make room for the
  breadcrumb.

**Content field:** `x 224–1440, y 56–900` (1216×844). Blueprint grid: 1px hairline lines,
24px pitch, both axes, full field, under everything.

**Certificate card:** `x 552–1112, y 241–715` (560×474), centered in the 1216×844 content
field with 328px clear on each side. Fill = substrate. Outer border 1px hairline. Inset
certificate rule 1px hairline, 10px inset (`x 562–1102, y 251–705`) — the double-frame a
calibration certificate uses. Four corner registration marks (blueprint crop-mark
convention): L-strokes, 1px accent-ink, 10px arm length, floating 6px outside each of the
card's four corners.

**Stamp badge** (the VOID mark, overlapping the card's top edge like a real ink stamp):
128×64 box at `x 952–1080, y 259–323`, rotated **−7°** about its center `(1016, 291)`.
Border: outer 2px solid error red, inner ring 1px solid error red inset 5px. Centered text
"VOID" — title role (20/600), IBM Plex Mono, error red, uppercase, letter-spacing 0.08em.

**Card content stack** (padding 32px, content box `x 584–1080`, width 496px), top-down from
`y=273`:

| Element | y-range | Height |
|---|---|---|
| Eyebrow: "RECORD LOOKUP — CALIBRATION VOID" | 273–289 | 16 |
| gap | — | 14 |
| Headline: "No record found for `ITM-4471`" (width capped 350px, `x 584–934`, clears the stamp's left edge at `x=952` by 18px) | 303–331 | 28 |
| gap | — | 12 |
| Body, 2 lines, full 496px width | 343–383 | 40 |
| gap | — | 20 |
| Divider (1px hairline, full width) | 403 | 1 |
| gap | — | 15 |
| Certificate fields table, 5 rows × 40px | 419–619 | 200 |
| gap | — | 24 |
| Actions row | 643–683 | 40 |

Table columns: label `x 584`, width 160 · gutter 24 · value `x 768`, width 312
(160+24+312 = 496, matches content width exactly).

**Certificate fields table** — the collision's device (measured value / tolerance /
checked-by / date), repurposed onto this lookup instead of a data point:

| Label (meta, uppercase) | Value (mono, body/data) |
|---|---|
| QUERIED VALUE | `ITM-4471` |
| MATCH RULE | exact, item_code |
| CHECKED BY | Atlas ERP · lookup service |
| CHECKED AT | 2026-08-14 · 09:41:32 UTC |
| RESULT | 0 records matched — VOID *(error red)* |

Row dividers: 1px hairline at `y 459, 499, 539, 579`.

**Actions**, `y 643–683` (40px tall, 16px gap between):
- Primary "Back to items" — `x 584`, width 152, fill accent-emphasis, label white, 2px
  radius, 14px/600 Inter.
- Secondary "Search again ⌘K" — `x 752`, width 190, fill substrate, 1px accent-ink border,
  label accent-ink, 2px radius, 14px/600 Inter, trailing "⌘K" in IBM Plex Mono.

Both get the standard focus ring on `:focus-visible`: 2px solid accent-ink, 2px offset.

---

## Type table

| Role | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 28px | Headline; wordmark; VOID stamp (mono substitution, see note) |
| Body/data | Inter Variable | 14px | 450 | 20px | Body copy, breadcrumb, nav labels, email |
| Body/data (mono) | IBM Plex Mono Variable | 14px | 450, tabular | 20px | Table values, `ITM-4471` inline in headline/breadcrumb |
| Meta | Inter Variable | 12px | 450 | 16px | Eyebrow line, table field labels (uppercase, 0.04–0.06em tracking) |
| Button label | Inter Variable | 14px | 600 | 20px | Both actions — borrowed weight (600 from Title role) at Body's size, not a fourth defined role |

**One deliberate exception:** the VOID stamp uses IBM Plex Mono (identifiers-only per the
system) rather than Inter, so it echoes the mono RESULT value in the certificate table below
it — same fact, two scales, same face. Everywhere else mono is reserved strictly for
identifiers and data values, per the system as given.

---

## Paired colors — computed, not rendered

Ran an OKLCH → linear-sRGB → WCAG relative-luminance conversion locally (not the dispatch's
pre-stated figures) to check every pair actually used on this surface:

| Pair | Computed ratio | Where used |
|---|---|---|
| primary text `oklch(0.20 0.01 58)` on substrate | **17.35:1** | Body copy, table QUERIED/MATCH/CHECKED values, breadcrumb current segment |
| secondary text `oklch(0.45 0.012 58)` on substrate | **7.14:1** | Eyebrow, table labels, breadcrumb parents, nav (inactive), email |
| error `oklch(0.5 0.18 25)` on substrate | **6.31:1** | Headline, VOID stamp, RESULT value, stamp border |
| accent-ink `oklch(0.42 0.09 58)` on substrate | **8.34:1** | Active nav label, "Sign out", secondary-button label/border, corner marks |
| accent-emphasis `oklch(0.55 0.13 58)` + white label | **5.06:1** | Primary button ("Back to items") |
| hairline `oklch(0.88 0.008 58)` on substrate | **1.38:1** | Blueprint grid, dividers, card border — decorative only, never load-bearing for text or a required control boundary |

**Flagging one discrepancy against the dispatch:** the dispatch states accent-ink ≈8.71:1
"on substrate." My computation gets 8.71:1 for accent-ink **on pure white**, but 8.34:1 on
the actual substrate token (which is off-white, not white — `rgb(252,250,248)` vs
`rgb(255,255,255)`). The gap is small and both numbers clear every threshold used here (body
text needs 4.5:1), but I'm using my own 8.34:1 since substrate, not white, is what's actually
behind accent-ink on this comp. Every pair above is a fresh computation, method noted, so it
can be checked rather than trusted.

---

## Content direction (one line)

Say plainly that the record never existed rather than implying loss ("No record found for
ITM-4471… there was nothing here to lose"), and let the certificate table carry the technical
proof of that claim — query, rule, checker, timestamp — so the VOID stamp reads as measured,
not decorative.

---

## Embarrassment-gate self-check

- Palette hexes: not rendered (spec mode) — every color above is the dispatch's own OKLCH
  token, none substituted; ratios recomputed from those exact values, checked against the
  palette table before writing this line.
- Type legibility: body/data floor is 14px at 7.14–17.35:1, meta floor is 12px at 7.14:1 —
  both clear 4.5:1 with margin; no text below 12px anywhere on the card.
- Bands: N/A — desktop tool-shaped surface, not mobile; sidebar + topbar chrome shown in
  full instead, per the dispatch's own scoping.
- Collision readable: yes — the certificate-fields table is a literal, checkable rendering
  of "measured value, tolerance, checked-by, date" applied to a lookup instead of a
  sensor reading; the stamp is flat-bordered (no blur/opacity fakery), keeping it
  data-brutalist rather than illustrative.
- No invented brand/logo, no fabricated data-as-fact: `ITM-4471` is a plausible item-code
  format already used elsewhere in this app's screenshots; "0 records matched" states a
  query result, not an invented metric; "Atlas ERP · lookup service" names a system actor,
  not a fabricated person (§14 N/A — no photo/face on this surface).
- Copy length: headline one line, body two sentences, table values one line each — all
  realistic for the space given.
- Would a designer put their name on this: yes, with the accent-ink discrepancy above
  disclosed rather than smoothed over.

---

## Returned

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/gauge-house/07-error-state.md`
- **Composition anchor:** `centered-statement`
- **Background mode:** `textured-surface`
- **One line:** A single stamped certificate card, centered on a blueprint grid, replaces the
  live silent-empty-form bug with a named error, proof of the query, and two exits — where a
  list/table sibling (e.g. items-list) would earn `dense-grid` and a form sibling would earn
  `stacked-center`, this is the one surface in the set whose entire content *is* the
  centered statement.
- **Could not fully satisfy:** the "checked-by" field has no human operator to name honestly
  (this is a system-side ID lookup, not a person-reviewed record), so it's filled with the
  system actor ("Atlas ERP · lookup service") rather than left blank or faked with a person
  — flagged as a deliberate substitution, not an oversight. The active-nav-row tint (accent-ink
  at 8% into substrate) is chrome state, not one of the six given palette tokens; it's
  disclosed above rather than presented as if it were.
