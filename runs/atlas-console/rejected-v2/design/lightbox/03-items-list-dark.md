# lightbox: Surface 3 of 7 — Items List

**Mode:** dark · **Canvas:** 1440×900 (fixed coded viewport; page scrolls inside it — see
"Row count and scroll" below) · **Composition anchor:** `dense-grid` · **Background mode:**
`flat-surface`

Same screen, same numbers, dark palette. All px values, column widths, row heights, and the
keyboard contract are unchanged from the light comp — only fills, text tokens, and the glass
formula's two-art-directions rule (`DIRECTION.md` §7: "light mode runs more opaque and less
blurred, dark mode runs less opaque and reads through more") differ.

## Layout — numbers

Base unit: 8px. Control floor: 44px (primary controls only — dense row-level controls use the
WCAG 2.5.8 spacing exception, noted per-instance below).

### The one glass object (reiterated briefly — full spec belongs to Surface 2)

- **Position:** `fixed; top:0; left:0; width:1440px; height:64px; z-index:50`. Same footprint
  as light — spans the full canvas width, above the rail and the table.
- **Fill:** `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` +
  `backdrop-filter: blur(20px)` — dark mode drops `saturate(140%)`, reads through more,
  per the concept's stated dark-mode rule for this one material. Border (bottom edge, 1px):
  `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)`.
- **Contents:** same as light — search trigger, quick-create, notifications, 36×36px icon
  buttons, 12px gap. Text scrim: same construction as light (a solid fill sitting directly
  behind each label), re-measured for the dark glass mix per `DIRECTION.md` §7's own
  instruction — the source table states the rule ("same scrim rule, re-measured on dark")
  without a separate numeric value, so this comp inherits the rule, not a restated formula;
  flagged for build-time measurement same as light.
- **Reduced motion:** same as light — instant opaque-bordered panel, never animates into a
  blur.
- **Below `y=64px`, nothing is glass.** Same rule as light, same line.

### Left rail — flat, opaque, icon + label

- `position: fixed; top:64px; left:0; width:240px; height:836px`. `substrate` fill, `1px solid
  hairline` right border. No blur.
- Same nav list as light: Home, Finance, **Inventory** (expanded, **Items** active),
  Procurement, Manufacturing, Sales, CRM, Projects, Quality, Maintenance, HR, Admin, Reporting,
  then **Help** pinned last.
- Active state ("Items"): `accent-tint-dark` fill, `accent-dark` text and icon, 3px
  `accent-dark` bar on the row's left edge.

### Main content column — `x:240–1440` (1200px), inner padding 32px → content 1136px wide

Same vertical rhythm as light, same y-offsets:

1. **Breadcrumb**, `y:96–112`: "Inventory" (`text-secondary`, link) / "Items" (`text-primary`,
   current), 12px/450.
2. 8px gap → **h1** "Items" 20px/600 `text-primary`, inline meta "37 items" 12px/450
   `text-secondary`. `y:120–148`.
3. 20px gap → **search/filter row**, `y:168–212`, 44px tall:
   - Search input, 320px × 44px, 12px radius, `1px solid hairline`, `substrate` fill, leading
     search icon, placeholder "Search items" 14px/450 `text-secondary`.
   - 16px gap → filter chips, 28px height, pill radius, `row-alt` fill, `1px solid hairline`,
     label 12px/450 `text-primary`, 16px "×" remove glyph in a 24px hit area (2.5.8 exception):
     **"Category: Hardware ×"**, 8px gap, **"Status: Low stock ×"**.
   - 8px gap → **"+ Filter"**, 32px height, 12px radius, `1px solid hairline`, no fill, label
     12px/600 `accent-dark`.
   - Row-end: **"+ New item"** primary button, 44px height, 12px radius, `accent-tint-dark`
     fill, label `accent-dark` 14px/600, 16px horizontal padding. **Token decision, stated
     explicitly:** `DIRECTION.md`'s dark table has no separate "emphasis" grade the way light
     does (`accent-emphasis`) — rather than invent an unlicensed fill+foreground pair, this
     button reuses the one documented dark pairing built for exactly this job:
     `accent-tint-dark` fill / `accent-dark` foreground, ~5:1 per the source table, not a new
     estimate.
4. 16px gap → table starts at `y:228`.

### The table

- Wrapper: `role="grid" aria-label="Items" aria-rowcount="37"`. Flat, opaque, no card, no
  shadow — the table is the substrate.
- **Column header row**, 40px height, `position: sticky; top:64px; z-index:20`, `substrate`
  fill, `1px solid hairline` bottom border, zero blur. Labels 12px/600. Sortable columns
  (`Item`, `Qty on hand`, `Reorder point`) carry a 12px chevron and `aria-sort`.
- **Column widths** (unchanged): Select 40 · Item 360 · Category 140 · Qty on hand 110 (right)
  · Reorder point 110 (right) · Vendor 180 · Status 100 · Actions 96 (right).
- **Body rows**, 40px height, alternating `substrate` / `row-alt` fill, `1px solid hairline`
  bottom border.
  - **Select** (40px): 16px checkbox, 24px hit area (2.5.8 exception).
  - **Item** (360px, `text-primary` 14px/450): code + name, one line, e.g. "ITM-BOLT · Hex
    Bolt M8×40, Zinc-Plated" — truncates with `title` on overflow.
  - **Category** (140px, `text-secondary`).
  - **Qty on hand** (110px, `text-primary`, tabular-nums, right-aligned).
  - **Reorder point** (110px, `text-secondary`, tabular-nums, right-aligned).
  - **Vendor** (180px, `text-secondary`).
  - **Status** (100px): dot/shape (8–10px) + 6px gap + label 14px/450 `text-primary`.
  - **Actions** (96px, right-aligned): revealed on `:hover` and `:focus-within`, never
    hover-only. Three icon buttons, 18px glyph in 24px target, 8px gaps (24px centre-to-centre,
    2.5.8): **Open**, **Edit**, **More**. `aria-label="Open ITM-BOLT"`, `"Edit ITM-BOLT"`,
    `"More actions for ITM-BOLT"`.
  - **Selected-row state:** `accent-tint-dark` fill replaces the zebra tint, 3px `accent-dark`
    bar on the left edge, checkbox filled `accent-dark`.

### Status vocabulary — same shapes, dark-adjusted values for 3:1 against dark row fills

Lightness raised so each hue still clears the 3:1 graphical floor against `substrate`
(~L0.155) / `row-alt` (~L0.205) — estimated, same disclosure convention as light, not
script-verified.

| Shape | Hue | Value (dark) | Meaning here |
|---|---|---|---|
| Solid filled circle | 150° | `oklch(0.72 0.14 150)` | In stock |
| Outlined circle | neutral | stroke `text-secondary` (dark) | Draft |
| Half-filled / striped circle | 80° | `oklch(0.75 0.15 80)` (estimated, verify at build) | Low stock |
| Solid triangle | 25° | `oklch(0.68 0.18 25)` | Out of stock |

## Interaction — `role="grid"` keyboard contract, unchanged from light

- **Arrow keys** move cell focus (Up/Down rows, Left/Right cells), roving `tabindex`.
- **Enter** opens the focused row's item detail screen — no inline-edit mode, same reasoning
  as light (a record's detail is content, gets its own opaque screen).
- **Space** toggles row selection without moving focus.
- **Shift + Arrow Up/Down** extends selection from the last-focused row.
- **Focus ring:** `2px solid accent-dark`, `2px` offset, `:focus-visible` only, inset within
  the focused cell, checked against both `substrate` and `row-alt`.

**No mobile safe-area bands** — desktop/web-only surface, same reserved-chrome reasoning as
light: the glass bar's 64px band and the table header's 40px sticky band are both reserved
space, never floated over content.

**Skip link:** same construction as light, dark values — `accent-dark` background,
substrate-dark text (`oklch(0.155 0.01 290)`, for max contrast on the light-valued accent
chip), 14px/600, "Skip to items table."

## Type

Identical scale to light — Inter Variable only, no mono face.

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / cell data | Inter Variable | 14px | 450 | 20px — numeric cells `tabular-nums` |
| Meta / breadcrumb / chip label | Inter Variable | 12px | 450 | 16px |
| Column header | Inter Variable | 12px | 600 | 16px |
| Command-bar label (on glass) | Inter Variable | 14px | 500 | 20px |
| Button label | Inter Variable | 14px | 600 | 20px |

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / table substrate | substrate | `oklch(0.155 0.01 290)` | text-primary `oklch(0.95 0.006 290)` | ~15:1 |
| Row banding | row-alt | `oklch(0.205 0.012 290)` | text-primary | ~13:1 |
| Category, Reorder point, Vendor, breadcrumb, chip label | text-secondary | `oklch(0.70 0.014 290)` | on substrate | ~6:1 |
| Row / card border, decorative only | hairline | `oklch(0.33 0.014 290)` | — decorative only, paired with row-alt band |
| Links, "+Filter", focus ring, sort chevrons | accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 |
| "+ New item" fill, selected-row fill, active-nav fill | accent-tint-dark | `oklch(0.28 0.045 290)` | accent-dark (foreground) | ~5:1 — documented dark pairing, reused rather than a new invented fill |
| **Glass command bar** | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `blur(20px)` | text on scrim (construction inherited from light, re-measured) | not restated numerically in source; flagged for build-time measurement |
| Status: in stock | — | `oklch(0.72 0.14 150)` | non-text, 3:1 graphical floor | estimated |
| Status: low stock | — | `oklch(0.75 0.15 80)` | non-text | estimated, verify at build (amber) |
| Status: out of stock | — | `oklch(0.68 0.18 25)` | non-text | estimated |
| Status: draft | — | stroke = text-secondary | non-text | inherits ~6:1 |

## Content direction

Identical copy to light — same item codes, names, categories, vendors, quantities; only the
palette changes between the two files, per the concept's own rule ("the opaque data layer is
one design in two palettes"). No new invented data introduced for dark.
