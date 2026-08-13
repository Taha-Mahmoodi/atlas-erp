# the yard: Surface 2 of 7 — Role Home
**Mode:** dark · **Canvas:** 1440×900, fixed coded viewport, full chrome · **Role:** Buyer (Procurement) · **Platform:** web/desktop-only

Same design, retuned palette — the token mechanism, grid, copy, and numbers below are
identical to the light spec (`02-role-home-light.md`); only lightness/chroma retunes per
`DIRECTION.md`'s "one design in two palettes" rule for this concept.

---

## 1. Layout move

Identical to light: left rail `240px` fixed, top header `64px` fixed, content area `1200×836px`,
padded `32px` → grid box `1136×772px`, `4` columns × `4` rows, `24px` gap.
- Column width `266px` · row height `175px`
- **Large lane** `556×374px` · **Small lane** `266×175px`

Same `grid-template-areas`:

```
procurement procurement inventory    inventory
procurement procurement inventory    inventory
sales       sales       finance      hr
sales       sales       admin        reporting
```

Card radius `16px` throughout, no glass, no hairline-brutalist sharpness. Card shadow reads
weaker on a dark substrate by construction, so it is paired with a `1px hairline` edge rather
than leaned on alone: `box-shadow: 0 1px 2px oklch(0 0 0 / 0.3), 0 8px 24px oklch(0 0 0 / 0.35)`
+ `1px solid hairline` `oklch(0.34 0.015 290)`. Card fill: `card` `oklch(0.24 0.012 290)`, on
`substrate` `oklch(0.19 0.012 290)`.

**Composition anchor:** `dense-grid` (same as light — the anchor is a structural property of
the layout, not the palette).
**Background mode:** `flat-surface` (same as light).

---

## 2. Left rail (240px)

- Brand mark, `64px` row, aligned to header height.
- Nav list, same role-derived order: **Home** (active) · Procurement · Inventory · Sales ·
  Finance · HR · Admin · Reporting. Each row `44px` min-height, `20px` icon + `8px` gap +
  `14px/500` label, `16px` horizontal padding. Icon+label at rest.
- Active state: `accent-tint-dark` `oklch(0.30 0.05 290)` pill fill, `accent-dark`
  `oklch(0.76 0.14 290)` icon + text. Inactive: `text-secondary` `oklch(0.68 0.015 290)` on
  transparent.
- Focus ring on every rail item: `2px solid accent-dark`, `2px` offset, `:focus-visible` only.

## 3. Top header (1200×64px)

- Left: `h1` "Home" (`title` 20px/600), `text-primary` `oklch(0.94 0.008 290)`. Skip link
  precedes the rail, visually hidden until `:focus`, targets `<main>`.
- Below: "Buyer · Procurement" (`meta` 12px/450, `text-secondary`).
- Center-left: search field `320×44px`, placeholder "Search or jump to… ⌘K", `card` fill,
  `hairline` `oklch(0.34 0.015 290)` border, `text-secondary` placeholder.
- Right, `44px`-tall, `16px` gaps: notification bell (accessible name "Notifications — 3
  pending across your lanes", `Pending`-hue badge count) · avatar-chip (`32px`, initials, no
  photo) · primary button "+ New" — `accent-dark` fill, `oklch(0.19 0.012 290)` text (dark
  text on the lighter accent, mirroring how the dark palette's accent already sits lighter than
  substrate), `44×44px` min, `16px` radius.

## 4. Categorical lane hues

Same formula and same seven hues as light — `hue = (10 + module-index × 32) mod 360`, but
`chroma 0.11`, `L 0.68` (dark, per the concept's stated dark categorical-hue lightness). Badge
fill at the formula's dark L/C/hue, icon glyph darker same-hue value, mirroring the dark
status-token pairing pattern (e.g. `Posted` dark: fill `L0.68` → text `L0.16`). Lane name stays
`text-primary`, never hue-colored, so legibility never depends on the categorical color.

| Lane | Size | Hue | Badge fill `oklch(0.68 0.11 H)` | Icon glyph `oklch(0.16 0.04 H)` | Est. ratio (badge) |
|---|---|---|---|---|---|
| Procurement | large | `10°` | `oklch(0.68 0.11 10)` | `oklch(0.16 0.04 10)` | ~5.4:1 |
| Inventory | large | `42°` | `oklch(0.68 0.11 42)` | `oklch(0.16 0.04 42)` | ~5.4:1 |
| Sales-demand | large | `66°` *(nudged from 74°, same reasoning as light — clears the 80° Pending hue by 14°)* | `oklch(0.68 0.11 66)` | `oklch(0.16 0.04 66)` | ~5.3:1 |
| Finance | small | `170°` | `oklch(0.68 0.11 170)` | `oklch(0.16 0.04 170)` | ~5.5:1 |
| HR | small | `234°` | `oklch(0.68 0.11 234)` | `oklch(0.16 0.04 234)` | ~5.5:1 |
| Admin | small | `312°` *(nudged from 298°, same reasoning as light — clears the 290° brand accent by 22°)* | `oklch(0.68 0.11 312)` | `oklch(0.16 0.04 312)` | ~5.3:1 |
| Reporting | small | `330°` | `oklch(0.68 0.11 330)` | `oklch(0.16 0.04 330)` | ~5.4:1 |

Ratios estimated per `DIRECTION.md §11`'s standing disclosure — no script pass has run yet.

## 5. The seven lanes

Same internal structure as light (badge+label / metric+comparison / divider / token row),
`24px` (large) / `20px` (small) padding. **Copy and numbers are identical to light** — this is
one design in two palettes, not a second art direction.

### Procurement — large, 556×374px
- **"18"** "Open purchase orders" · **"↑ 3 from last week"**.
- Tokens (8): `Pending`×4, `Draft`×2, `Overdue`×1, `Posted`×1.
- Example: *"Pending — Purchase Order `PO-2026-00147`, awaiting vendor confirmation"*.

### Inventory — large, 556×374px
- **"6"** "Items below reorder point" · **"↓ 2 from last week"**.
- Tokens (6): `Overdue`×3, `Pending`×2, `Draft`×1.
- Example: *"Overdue — Item `ITM-04821` below reorder point, 3 days"*.

### Sales-demand — large, 556×374px
- **"27"** "Open sales orders awaiting fulfillment" · **"↑ 5 from last week"**.
- Tokens (7): `Pending`×4, `Posted`×2, `Draft`×1.
- Example: *"Pending — Sales Order `SO-2026-00892`, awaiting warehouse allocation"*.

### Finance — small, 266×175px (quiet)
- **"3"** "Journal entries pending review" · **"steady — no change from last week"**.
- Token (1, calm neutral `Draft` shape): *"3 journal entries pending review, none overdue"*.

### HR — small, 266×175px (quiet)
- **"0"** "Items assigned to you" · **"steady — no change from last week"**.
- Token (1, calm neutral): *"Nothing pending in HR — 0 items assigned to you"*.

### Admin — small, 266×175px (quiet)
- **"1"** "System notices" · **"steady — no change from last week"**.
- Token (1, calm neutral): *"1 system notice — no action required, view in Admin"*.

### Reporting — small, 266×175px (quiet)
- **"4"** "Saved reports" · **"steady — no change from last week"**.
- Token (1, calm neutral): *"4 saved reports — last run 2 days ago"*.

## 6. Signal-token component

Identical mechanism to light, dark values only.

- **Solid states** (`Pending`, `Posted`, `Overdue`, `Closed`): `28×28px` rounded square, `8px`
  radius, `14px` glyph centered in the paired text color.
- **`Draft` / calm-neutral**: same footprint, `2px` dashed ring, no solid fill — shape carries
  "not yet committed" before hue does.
- Row gap `8px`, interactive hit target `44×44px` centered on the visible chip.
- Hover-reveal tooltip: `card` fill `oklch(0.24 0.012 290)`, `hairline` border
  `oklch(0.34 0.015 290)`, `body` 14px/450 text, `mono-identifier` run in JetBrains Mono
  Variable 13px/500. Same string is the `aria-label`.
- Focus ring: `2px solid accent-dark` `oklch(0.76 0.14 290)`, `2px` offset, `:focus-visible`.
  Checked against `card` `oklch(0.24 0.012 290)` (large lightness gap, `0.76` vs `0.24` — high
  contrast) **and** against every dark token fill (`0.7`, `0.68`, `0.65`, `0.3`, `0.5`) — the
  ring's `L0.76` sits lighter than all five, so it never merges with the fill it circles.

## 7. Status-token vocabulary (as specified, dark pairs)

| State | Fill | Text/glyph | Glyph |
|---|---|---|---|
| Draft | `oklch(0.3 0.01 290)` | `oklch(0.85 0.01 290)` | dashed ring, pencil |
| Pending | `oklch(0.7 0.13 80)` | `oklch(0.18 0.02 80)` | clock |
| Posted/Success | `oklch(0.68 0.14 150)` | `oklch(0.16 0.02 150)` | check |
| Overdue/Error | `oklch(0.65 0.17 25)` | `oklch(0.16 0.02 25)` | exclaim |
| Closed | `oklch(0.5 0.01 290)` | white | lock |

## 8. Type table

Identical faces, sizes, weights, line-heights to light — type does not retune between modes.

| Level | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| metric-display | Inter Variable, tabular | 34px | 700 | 40px (1.18) | lane metric numbers |
| title | Inter Variable | 20px | 600 | 28px (1.4) | h1 "Home" |
| lane-header | Inter Variable | 15px | 600 | 20px (1.33) | lane names |
| body/data | Inter Variable, tabular | 14px | 450 | 20px (1.43) | lane subtitles, tooltip body |
| meta | Inter Variable | 12px | 450 | 16px (1.33) | comparisons, role context |
| mono-identifier | JetBrains Mono Variable | 13px | 500 | 18px (1.38) | document IDs inside tooltips only |

## 9. Palette used on this surface (dark, paired, with ratios)

| Token | Value | Paired foreground | Est. ratio | Used for |
|---|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | text-primary `oklch(0.94 0.008 290)` | ~14:1 | app background |
| card | `oklch(0.24 0.012 290)` | text-primary | ~13:1 | all seven lane cards |
| text-secondary | `oklch(0.68 0.015 290)` | on card | ~6:1 | comparisons, meta, placeholders |
| hairline | `oklch(0.34 0.015 290)` | decorative-only | same caveat as light | dividers, card edge, search-field border |
| accent-dark | `oklch(0.76 0.14 290)` | on substrate | ~6:1 | primary button, rail active state, focus ring |
| accent-tint-dark | `oklch(0.30 0.05 290)` | accent-dark | ~5:1 | rail active pill background |

No dark equivalent of `accent-emphasis` is defined in `DIRECTION.md` for this concept, and none
is needed here for the same reason as light — no element on this surface is large/bold enough
to justify a borderline pairing when `accent-dark` (`~6:1`, verified) already covers it.

## 10. Access

Identical to light — `role="grid"` not used here (real grids live one level down); every
icon-only control carries a full state+record accessible name; `44px` control floor and `8px`
base unit throughout; skip link, one `h1`, `<main>` landmark; focus ring `2px solid accent-dark`,
`2px` offset, `:focus-visible`, verified against `card` and every dark token fill (§6).

## 11. Content direction

Identical to light — real-shaped buyer numbers with a comparison on every one, quiet lanes each
hold one calm token instead of sitting empty, terminology lock honored (`item`, `vendor`,
`warehouse`, `journal entry`), no invented brand, logo, or person.

---

**Self-check before return:** every hex above was read back against `DIRECTION.md §6`'s dark
palette table and the dark status-token pairs — no value carried over from light by assumption.
The two nudged categorical hues (`Sales 66°`, `Admin 312°`) match light exactly, since hue
rotation is not a mode-dependent value in this concept — only `L` and the paired text/glyph `L`
retune.
