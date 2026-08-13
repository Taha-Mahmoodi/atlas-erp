# lightbox: Surface 3 of 7 — Items List

**Mode:** light · **Canvas:** 1440×900 (fixed coded viewport; page scrolls inside it — see
"Row count and scroll" below) · **Composition anchor:** `dense-grid` · **Background mode:**
`flat-surface`

Inventory > Items. The collision's whole argument lives on this screen more than any other
in the set: the glass command bar floats fixed at the very top, and everything below `y=64px`
— left rail, title, filters, and all 37 rows of the table — is flat, opaque, unblurred data.
The glass never touches a row. That boundary is drawn once, in pixels, below.

## Layout — numbers

Base unit: 8px. Control floor: 44px (primary controls only — dense row-level controls use the
WCAG 2.5.8 spacing exception, noted per-instance below).

### The one glass object (reiterated briefly — full spec belongs to Surface 2)

- **Position:** `fixed; top:0; left:0; width:1440px; height:64px; z-index:50`. Spans the full
  canvas width, above the rail and above the table — nothing on this screen renders above it.
- **Fill:** `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` +
  `backdrop-filter: blur(20px) saturate(140%)`. Border (bottom edge only, 1px):
  `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)`.
- **Contents** (unchanged from Surface 2): search trigger left (`⌘K Search or jump to…`,
  320px, opens the app-wide search/jump), quick-create `+` icon button and notifications bell
  right, 36×36px each, 12px gap. Every label sits on its own scrim,
  `color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)`, measured against the busiest
  table row scrolling directly beneath it (worst-frame case per `ACCESS.md` decision row 4).
- **Reduced motion:** blur-in on load degrades to an instant opaque-bordered panel — never
  animates into or out of a blur (`ACCESS.md` decision row 11).
- **Below `y=64px`, nothing is glass.** Left rail, title, search/filter row, and table are all
  `substrate`/`row-alt` fills with zero `backdrop-filter`. This line is the whole comp.

### Left rail — flat, opaque, icon + label (discoverability path, not the fast path)

- `position: fixed; top:64px; left:0; width:240px; height:836px`. `substrate` fill, `1px solid
  hairline` right border. No blur.
- 16px padding. Rows: Home, Finance, **Inventory** (expanded — chevron down; sub-items
  Warehouses, Stock moves, and **Items**, the active one), Procurement, Manufacturing, Sales,
  CRM, Projects, Quality, Maintenance, HR, Admin, Reporting. Each row 44px height, 20px icon +
  8px gap + 14px/450 label, `text-primary`.
- Active state ("Items"): `accent-tint` fill, `accent-ink` text and icon, 3px `accent-ink` bar
  on the row's left edge.
- Flex spacer, then **Help** pinned last — same relative position on every screen, both
  concepts (`ACCESS.md` decision row 8).

### Main content column — `x:240–1440` (1200px), inner padding 32px → content 1136px wide

Content starts at `y=64+32=96`.

1. **Breadcrumb**, `y:96–112`: "Inventory" (`text-secondary`, link) / "Items" (`text-primary`,
   current) — 12px/450.
2. 8px gap → **h1** "Items" 20px/600 `text-primary`, inline with meta "37 items" 12px/450
   `text-secondary` (baseline-aligned, 12px gap after the h1). `y:120–148`. The one h1 on the
   screen.
3. 20px gap → **search/filter row**, `y:168–212` (44px tall, matches the control floor since
   the search input is a primary control):
   - Search input, 320px × 44px, 12px radius, `1px solid hairline`, `substrate` fill, 12px
     padding, leading 16px search icon, placeholder "Search items" 14px/450 `text-secondary`.
     `type="search"`.
   - 16px gap → filter chips, vertically centered in the 44px row, chip height 28px, pill
     radius (999px), `row-alt` fill, `1px solid hairline`, label 12px/450 `text-primary`, 6px
     gap to a 16px "×" remove glyph (real `<button aria-label="Remove filter: Category —
     Hardware">`, 24px hit area — WCAG 2.5.8 exception, not the 44px floor, since this is an
     icon-only control inside a dense cluster): **"Category: Hardware ×"**, 8px gap,
     **"Status: Low stock ×"**.
   - 8px gap → **"+ Filter"** tertiary button, 32px height (clears the 24×24 general target
     floor; not gated by the 44px primary-control rule since it isn't a primary action), 12px
     radius, `1px solid hairline`, no fill, label 12px/600 `accent-ink`.
   - Row-end, right-aligned: **"+ New item"** primary button, 44px height, 12px radius, solid
     `accent-emphasis` fill, label white 14px/600, 16px horizontal padding. The one filled CTA
     on this screen — everything else here is line-level.
4. 16px gap → table starts at `y:228`.

### The table

- Wrapper: `role="grid" aria-label="Items" aria-rowcount="37"`. Flat, opaque, no card, no
  shadow, no rounded container — the table *is* the substrate, edge to edge within the 1136px
  content column.
- **Column header row** (`role="row"`, cells `role="columnheader"`), 40px height,
  `position: sticky; top:64px; z-index:20` — sticks directly under the fixed glass bar as the
  page scrolls, and is itself `substrate` fill with `1px solid hairline` bottom border, zero
  blur. Labels 12px/600 (meta size, weight stepped up from the scale's 450 to carry header
  hierarchy — the one deliberate weight exception on this screen, still Inter Variable, no new
  face, no new size). Sortable columns (`Item`, `Qty on hand`, `Reorder point`) carry a 12px
  chevron and `aria-sort`.
- **Column widths** (sum 1136px): Select 40 · Item 360 · Category 140 · Qty on hand 110
  (right) · Reorder point 110 (right) · Vendor 180 · Status 100 · Actions 96 (right).
- **Body rows** (`role="row" aria-selected`), 40px height, alternating `substrate` / `row-alt`
  fill (the density note below explains why this never gets heavier at row 37 than at row 4),
  `1px solid hairline` bottom border — hairline is the secondary boundary signal, banding is
  the primary one, per the palette's own "pair with row-alt tint" caveat.
  - **Select** (40px): 16px checkbox, 24px hit area centered in the 40px row (2.5.8 exception,
    same reasoning as the filter-chip remove glyph — a dense grid's row controls are not
    primary controls).
  - **Item** (360px, `role="gridcell"`, `text-primary` 14px/450): code + name, one line,
    e.g. "ITM-BOLT · Hex Bolt M8×40, Zinc-Plated" — truncates with `title` attribute on
    overflow, never wraps the row taller.
  - **Category** (140px, `text-secondary`).
  - **Qty on hand** (110px, `text-primary`, `font-variant-numeric: tabular-nums`,
    right-aligned).
  - **Reorder point** (110px, `text-secondary`, tabular-nums, right-aligned — the reference
    value, secondary to the live quantity next to it).
  - **Vendor** (180px, `text-secondary`).
  - **Status** (100px): dot/shape (8–10px) + 6px gap + label 14px/450 `text-primary`. See
    "Status vocabulary" below for shape/hue/value.
  - **Actions** (96px, right-aligned): revealed on `:hover` **and** `:focus-within` — never
    hover-only. Three icon buttons, 18px glyph in a 24px target, 8px gaps (24px centre-to-
    centre, WCAG 2.5.8 exception): **Open** (arrow-in), **Edit** (pencil), **More** (kebab).
    Real accessible names naming the record, never bare verbs: `aria-label="Open ITM-BOLT"`,
    `"Edit ITM-BOLT"`, `"More actions for ITM-BOLT"`.
  - **Selected-row state:** `accent-tint` fill replaces the zebra tint, 3px `accent-ink` bar on
    the row's left edge, checkbox filled `accent-ink`.

### Status vocabulary — shape carries the meaning, never color alone

Same generic four-state grammar as the rest of the run, mapped onto stock state on this
screen. Values estimated per this run's coded-comp disclosure convention (`DIRECTION.md`
§11) — not script-verified; flagged for the same build-time re-measurement as the palette's
own borderline `accent-emphasis` pairing.

| Shape | Hue | Value (light) | Meaning here | Accessible name pattern |
|---|---|---|---|---|
| Solid filled circle | 150° | `oklch(0.60 0.14 150)` | In stock | "In stock — ITM-BOLT" |
| Outlined circle (stroke only, no fill) | neutral | stroke `text-secondary` | Draft — item created, not yet stocked/vendored | "Draft — ITM-0011" |
| Half-filled / striped circle | 80° | `oklch(0.62 0.15 80)` (estimated — amber hues read lower-contrast at equal L than the other three; verify at build) | Low stock — at or below reorder point | "Low stock — ITM-0002" |
| Solid triangle | 25° | `oklch(0.55 0.20 25)` | Out of stock | "Out of stock — ITM-0003" |

Each dot's fill/stroke is checked as a non-text graphical element against its row fill
(`substrate` ~L0.99 / `row-alt` ~L0.965) at the 3:1 graphical floor, not the 4.5:1 text floor
— the status *label* next to it is always plain `text-primary`, so no colored text ever
carries the state alone either.

### Row count and scroll — the density proof

37 rows total. The first ~15 are visible in the 900px canvas without scrolling
(`96 + 16 + 8 + 28 + 20 + 44 + 16 + 40 = 268px` of header above the table body; remaining
`900 - 268 = 632px` ÷ 40px row height ≈ 15 rows). The other 22 are reached by scrolling the
page — the glass command bar and the table's own column header both stay pinned throughout.

Sample rows (14 shown; rows 15–37 continue the identical flat row template — real item names
across the same category mix, no placeholder rows, no ellipsis truncating the list itself,
only long cell text truncates):

| Item | Category | Qty on hand | Reorder point | Vendor | Status |
|---|---|---:|---:|---|---|
| ITM-BOLT · Hex Bolt M8×40, Zinc-Plated | Fasteners | 1,240 | 500 | Meridian Fasteners Co. | ● In stock |
| ITM-0002 · Ball Valve 1in, Brass | Plumbing | 86 | 100 | Corenta Supply | ◐ Low stock |
| ITM-0003 · USB-C Cable, 2m | Electronics | 0 | 50 | Northline Components | ▲ Out of stock |
| ITM-0004 · Safety Goggles, Clear | Safety Equipment | 312 | 150 | Guardwell Industrial | ● In stock |
| ITM-0005 · Cardboard Carton, 12×12×12 | Packaging | 4,500 | 1,000 | Delta Pack Supply | ● In stock |
| ITM-0006 · Stainless Steel Sheet, 4×8ft | Raw Materials | 22 | 30 | Ferrotech Metals | ◐ Low stock |
| ITM-0007 · Nitrile Gloves, Box of 100 | Safety Equipment | 640 | 200 | Guardwell Industrial | ● In stock |
| ITM-0008 · Ethernet Cable Cat6, 10m | Electronics | 0 | 40 | Northline Components | ▲ Out of stock |
| ITM-0009 · Industrial Degreaser, 5gal | Chemicals | 18 | 10 | Solvex Chemical | ● In stock |
| ITM-0010 · Wing Nut M6 | Fasteners | 2,100 | 800 | Meridian Fasteners Co. | ● In stock |
| ITM-0011 · Router Bit Set, 12pc | MRO/Tools | — | — | — | ○ Draft |
| ITM-0012 · Copier Paper, A4, Case | Office Supplies | 240 | 100 | Baymark Office Partners | ● In stock |
| ITM-0013 · Pressure Gauge 0–200psi | MRO/Tools | 44 | 50 | Corenta Supply | ◐ Low stock |
| ITM-0014 · Anti-Static Wrist Strap | Electronics | 96 | 40 | Northline Components | ● In stock |

**The density proof, stated plainly:** every one of these 40 possible rows uses the exact same
markup — one `role="row"`, seven flat cells, one hairline, one zebra fill. No wrapper, no
shadow, no card appears at row 37 that wasn't already in row 4. The opaque data layer is
"fully opaque and flat by construction," so the row count is free (`DIRECTION.md` §7,
"Style-under-density").

## Interaction — `role="grid"` keyboard contract, stated explicitly

- **Arrow keys** move cell focus: Up/Down between rows, Left/Right between cells in a row.
  Roving `tabindex` — one cell in the grid is `tabindex="0"` at a time, the rest `-1"`.
- **Enter** opens the focused row's item detail screen. There is no inline-edit mode in this
  grid by design — the concept's own rule is that a record's detail is content and gets its
  own opaque screen, never a floating panel, so "opens" is the operative half of the contract
  here rather than "edits in place."
- **Space** toggles selection (`aria-selected`) on the focused row without moving focus.
- **Shift + Arrow Up/Down** extends the selection range from the last-focused row.
- **Focus ring:** `2px solid accent-ink`, `2px` offset, `:focus-visible` only, rendered inset
  within the focused cell's own padding so it's visible against both `substrate` and `row-alt`
  fills and never gets clipped by the row's 1px hairline border.

**No mobile safe-area bands apply** — desktop/web-only surface. The equivalent "reserved, not
floating" rule (`ACCESS.md` decision row 5) is satisfied the same way twice on this screen:
the glass command bar occupies a real 64px band that all content is offset below and never
overlaid, and the table's own sticky header reserves its 40px height the same way as the page
scrolls beneath it.

**Skip link:** first in DOM/tab order, visually hidden until `:focus-visible`, then fixed
`top:16px; left:16px`, `accent-ink` background, white text, 14px/600, 8px 16px padding, 8px
radius. Copy: "Skip to items table" — targets the grid's first cell.

## Type

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / cell data | Inter Variable | 14px | 450 | 20px — numeric cells `tabular-nums` |
| Meta / breadcrumb / chip label | Inter Variable | 12px | 450 | 16px |
| Column header (meta size, stepped weight) | Inter Variable | 12px | 600 | 16px |
| Command-bar label (on glass) | Inter Variable | 14px | 500 | 20px |
| Button label | Inter Variable | 14px | 600 | 20px |

No JetBrains Mono or any second face anywhere on this screen — identifiers get tabular
figures from Inter's own numeric OpenType feature, not a monospace substitution.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / table substrate | substrate | `oklch(0.99 0.003 290)` | text-primary `oklch(0.20 0.012 290)` | ~16:1 |
| Row banding | row-alt | `oklch(0.965 0.006 290)` | text-primary | ~15:1 |
| Category, Reorder point, Vendor, breadcrumb, chip label | text-secondary | `oklch(0.47 0.015 290)` | on substrate | ~6.3:1 |
| Row / card border, decorative only | hairline | `oklch(0.90 0.008 290)` | — sub-3:1, paired with the row-alt band, never the sole boundary signal |
| Links, "+Filter", focus ring | accent-ink | `oklch(0.43 0.15 290)` | white / on substrate | ~7.2:1 |
| "+ New item" button fill | accent-emphasis | `oklch(0.52 0.18 290)` | white (button label) | ~4.9:1 — borderline, flagged unverified per source RISK 4; label never drops below 14px |
| Selected-row fill, active-nav fill | accent-tint | `oklch(0.95 0.03 290)` | accent-ink | ~6:1 |
| **Glass command bar** | `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` + `blur(20px) saturate(140%)` | text on its own scrim, `color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)` | measured against worst-frame scroll; re-measurement flagged, not assumed passing |
| Status: in stock | — | `oklch(0.60 0.14 150)` | non-text, 3:1 graphical floor | estimated |
| Status: low stock | — | `oklch(0.62 0.15 80)` | non-text | estimated, verify at build (amber) |
| Status: out of stock | — | `oklch(0.55 0.20 25)` | non-text | estimated |
| Status: draft | — | stroke = text-secondary | non-text | inherits text-secondary's ~6.3:1 |

## Content direction

Real inventory nouns throughout — no "product," no "SKU," "vendor" never "supplier." Item
names and codes are plausible-length real-domain strings (`ITM-BOLT`, "Hex Bolt M8×40,
Zinc-Plated"), not lorem. Quantities and reorder points are structural sample data
consistent within this one spec, not a marketing claim. No invented brand name beyond
"Atlas" itself, no logo. "37 items" is the same count as the row total stated above it — no
second, unverifiable stat invented to sit next to it.
