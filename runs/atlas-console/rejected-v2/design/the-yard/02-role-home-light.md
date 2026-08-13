# the yard: Surface 2 of 7 — Role Home
**Mode:** light · **Canvas:** 1440×900, fixed coded viewport, full chrome · **Role:** Buyer (Procurement) · **Platform:** web/desktop-only

This is the anchor screen of the 7-surface set — the first authenticated thing the operator
sees, forty things waiting at 9am. It renders as a bento grid of unequal lanes, one lane per
module this role actually touches, sized by how often the buyer uses it — not alphabetically.

---

## 1. Layout move

**Chrome:** left rail `240px` fixed × full height. Top header `64px` fixed, spanning the
remaining `1200px`. Content area below the header: `1200×836px`.

**Grid:** content area padded `32px` all sides → grid box `1136×772px`. `4` columns × `4`
rows, `24px` gap (`3× the 8px base unit`).
- Column width: `(1136 − 72) / 4 = 266px`
- Row height: `(772 − 72) / 4 = 175px`
- **Large lane** (2 col × 2 row span): `556 × 374px`
- **Small lane** (1 col × 1 row span): `266 × 175px`

**Lane placement** (`grid-template-areas`, top-left origin):

```
procurement procurement inventory    inventory
procurement procurement inventory    inventory
sales       sales       finance      hr
sales       sales       admin        reporting
```

Card radius `16px` throughout (no glass, no hairline-brutalist sharpness — every corner soft).
Card shadow: `0 1px 2px oklch(0 0 0 / 0.05), 0 8px 24px oklch(0 0 0 / 0.06)`. Card fill: `card`
token, `oklch(1 0 0)`, on `substrate` `oklch(0.985 0.004 290)`.

**Composition anchor:** `dense-grid` — the seven-lane grid *is* the canvas; rail and header are
subordinate margin around it, not competing focal points.
**Background mode:** `flat-surface` — one solid substrate, all seven cards inline on it, no
image, no gradient field, no texture.

---

## 2. Left rail (240px)

- Brand mark, `64px` row, aligned to header height.
- Nav list, role-derived order (most-frequent module first, not alphabetical), each row `44px`
  min-height (control floor): `20px` icon + `8px` gap + `14px/500` label, `16px` horizontal
  padding. Icon+label at rest — never icon-only in the rail.
- Order: **Home** (active) · Procurement · Inventory · Sales · Finance · HR · Admin · Reporting.
- Active state: `accent-tint` `oklch(0.94 0.035 290)` pill fill, `accent-ink` `oklch(0.44 0.15 290)`
  icon + text. Inactive: `text-secondary` `oklch(0.46 0.02 290)` icon + text on transparent.
- Focus ring on every rail item: `2px solid accent-ink`, `2px` offset, `:focus-visible` only.

## 3. Top header (1200×64px)

- Left: `h1` "Home" (`title` 20px/600), `text-primary`. One `h1` on the page, nothing else
  competes for it. Skip link "Skip to main content" precedes the rail, visually hidden until
  `:focus`, targets `<main>` (the grid).
- Below the `h1`, inline: "Buyer · Procurement" (`meta` 12px/450, `text-secondary`) — role
  context, not a greeting, no marketing filler.
- Center-left: search field, `320×44px`, placeholder "Search or jump to… ⌘K", `card` fill,
  `hairline` `oklch(0.89 0.01 290)` border, `text-secondary` placeholder. ⌘K opens the same
  command palette from anywhere on the console, not only from this field.
- Right, `44px`-tall controls, `16px` gaps: notification bell (icon-only, accessible name
  "Notifications — 3 pending across your lanes", small `Pending`-hue badge count) · avatar-chip
  (`32px` circle, initials, no photo) · primary button "+ New" — `accent-ink` fill, white text,
  `44×44px` min, `16px` radius.

## 4. Categorical lane hues

Formula: `hue = (10 + module-index × 32) mod 360`, `chroma 0.11`, `L 0.60` (light). Each lane
header carries a `28px` circular badge: fill at the formula's `L/C/hue`, icon glyph at a darker
same-hue value — mirroring the status-token contrast pattern (mid-L fill, low-L glyph), not the
formula's L/C used directly as text color (15px/600 at L0.60 does not clear 4.5:1 reliably on
white). Lane *name* stays `text-primary` regardless of hue, so legibility never depends on the
categorical color.

| Lane | Size | Hue | Badge fill `oklch(0.60 0.11 H)` | Icon glyph `oklch(0.20 0.06 H)` | Est. ratio (badge) |
|---|---|---|---|---|---|
| Procurement | large | `10°` | `oklch(0.60 0.11 10)` | `oklch(0.20 0.06 10)` | ~4.8:1 |
| Inventory | large | `42°` | `oklch(0.60 0.11 42)` | `oklch(0.20 0.06 42)` | ~4.8:1 |
| Sales-demand | large | `66°` *(nudged from 74° — clears the 80° Pending-token hue by 14°, was 6°)* | `oklch(0.60 0.11 66)` | `oklch(0.20 0.06 66)` | ~4.7:1 |
| Finance | small | `170°` | `oklch(0.60 0.11 170)` | `oklch(0.20 0.06 170)` | ~4.9:1 |
| HR | small | `234°` | `oklch(0.60 0.11 234)` | `oklch(0.20 0.06 234)` | ~4.9:1 |
| Admin | small | `312°` *(nudged from 298° — clears the 290° brand accent by 22°, was 8°)* | `oklch(0.60 0.11 312)` | `oklch(0.20 0.06 312)` | ~4.7:1 |
| Reporting | small | `330°` | `oklch(0.60 0.11 330)` | `oklch(0.20 0.06 330)` | ~4.8:1 |

Ratios are estimated per `DIRECTION.md §11`'s standing disclosure (no script pass yet), same
caveat as `accent-emphasis`.

## 5. The seven lanes

Every lane, large or small: `24px` (large) / `20px` (small) internal padding. Row 1 = badge +
lane-header label. Row 2 = metric-display + comparison (comparison is never omitted — a bare
number is the analytics-cliché this system fences against). Row 3 = `hairline` divider,
decorative-only. Row 4 = signal-token row, wrapping.

### Procurement — large, 556×374px
- Metric: **"18"** (`metric-display` 34px/700 tabular) · "Open purchase orders" (`body` 14px/450)
  · comparison **"↑ 3 from last week"** (`meta` 12px/450, `text-secondary`).
- Tokens (8, two rows of four): `Pending`×4, `Draft`×2, `Overdue`×1, `Posted`×1.
- Example accessible name (hover-reveal, also the token's `aria-label`): *"Pending — Purchase
  Order `PO-2026-00147`, awaiting vendor confirmation"* — identifier in `mono-identifier`
  13px/500 inside the tooltip only, never in the token itself.

### Inventory — large, 556×374px
- Metric: **"6"** · "Items below reorder point" · comparison **"↓ 2 from last week"** (fewer is
  the good direction here, stated as-is, not re-signed).
- Tokens (6): `Overdue`×3, `Pending`×2, `Draft`×1.
- Example: *"Overdue — Item `ITM-04821` below reorder point, 3 days"*.

### Sales-demand — large, 556×374px
- Metric: **"27"** · "Open sales orders awaiting fulfillment" · comparison **"↑ 5 from last
  week"**.
- Tokens (7): `Pending`×4, `Posted`×2, `Draft`×1.
- Example: *"Pending — Sales Order `SO-2026-00892`, awaiting warehouse allocation"*.

### Finance — small, 266×175px (quiet — buyer rarely touches Finance)
- Metric: **"3"** · "Journal entries pending review" · comparison **"steady — no change from
  last week"**.
- Token (1, calm neutral — the `Draft` shape stands in for "nothing urgent" per the concept's
  own rule that no lane is ever empty): *"3 journal entries pending review, none overdue"*.

### HR — small, 266×175px (quiet)
- Metric: **"0"** · "Items assigned to you" · comparison **"steady — no change from last week"**.
- Token (1, calm neutral): *"Nothing pending in HR — 0 items assigned to you"*.

### Admin — small, 266×175px (quiet)
- Metric: **"1"** · "System notices" · comparison **"steady — no change from last week"**.
- Token (1, calm neutral): *"1 system notice — no action required, view in Admin"*.

### Reporting — small, 266×175px (quiet)
- Metric: **"4"** · "Saved reports" · comparison **"steady — no change from last week"**.
- Token (1, calm neutral): *"4 saved reports — last run 2 days ago"*.

## 6. Signal-token component

The one atomic status unit, used identically in every lane and everywhere else in the system.

- **Solid states** (`Pending`, `Posted`, `Overdue`, `Closed`): `28×28px` rounded square, `8px`
  corner radius, glyph `14px` centered in the paired text color.
- **`Draft` / calm-neutral state**: same `28×28px` footprint, but a `2px` **dashed ring**, no
  solid fill — a distinct silhouette so "not yet committed / nothing urgent" is legible by shape
  alone before hue is even read (shape **and** hue, never hue alone, per `§10`).
- Row gap `8px`. Interactive hit target `44×44px` (control floor) centered on the visible token
  — the visible chip stays small and dense; the click/tap/focus target does not.
- Hover-reveal tooltip: appears below the token after a short delay, `card` fill, `hairline`
  border, `body` 14px/450 text with the `mono-identifier` run in `JetBrains Mono Variable`
  13px/500. Same string is the token's `aria-label`, so keyboard and screen-reader access get
  the identical sentence a mouse hover gets — never an icon-only, colorless name.
- Focus ring: `2px solid accent-ink` `oklch(0.44 0.15 290)`, `2px` offset, `:focus-visible`.
  Checked against `card` white (offset ring sits on the white gap outside the chip — high
  contrast, no issue) **and** against each state's own fill, since accent-ink's hue (`290°`) is
  off-axis from every status hue (`80°`, `150°`, `25°`, neutral) and its lightness (`0.44`)
  matches none of the fills' lightness values (`0.62`, `0.58`, `0.55`, `0.35`) — the ring never
  reads as part of the token it is circling.

## 7. Status-token vocabulary (as specified, light pairs)

| State | Fill | Text/glyph | Glyph |
|---|---|---|---|
| Draft | `oklch(0.93 0.006 290)` | `oklch(0.4 0.01 290)` | dashed ring, pencil |
| Pending | `oklch(0.62 0.14 80)` | `oklch(0.2 0.03 80)` | clock |
| Posted/Success | `oklch(0.58 0.15 150)` | `oklch(0.18 0.03 150)` | check |
| Overdue/Error | `oklch(0.55 0.19 25)` | white | exclaim |
| Closed | `oklch(0.35 0.008 290)` | white | lock |

## 8. Type table

| Level | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| metric-display | Inter Variable, tabular | 34px | 700 | 40px (1.18) | lane metric numbers |
| title | Inter Variable | 20px | 600 | 28px (1.4) | h1 "Home" |
| lane-header | Inter Variable | 15px | 600 | 20px (1.33) | lane names |
| body/data | Inter Variable, tabular | 14px | 450 | 20px (1.43) | lane subtitles, tooltip body |
| meta | Inter Variable | 12px | 450 | 16px (1.33) | comparisons, role context |
| mono-identifier | JetBrains Mono Variable | 13px | 500 | 18px (1.38) | document IDs inside tooltips only |

## 9. Palette used on this surface (light, paired, with ratios)

| Token | Value | Paired foreground | Est. ratio | Used for |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | text-primary `oklch(0.21 0.015 290)` | ~15:1 | app background |
| card | `oklch(1 0 0)` | text-primary | ~16:1 | all seven lane cards |
| text-secondary | `oklch(0.46 0.02 290)` | on card | ~6.5:1 | comparisons, meta, placeholders |
| hairline | `oklch(0.89 0.01 290)` | decorative-only | sub-3:1 | dividers, search-field border — never a sole state signal |
| accent-ink | `oklch(0.44 0.15 290)` | white / on card | ~7:1 | primary button, rail active state, focus ring |
| accent-tint | `oklch(0.94 0.035 290)` | accent-ink | ~6:1 | rail active pill background |

`accent-emphasis` (`~4.8:1`, flagged borderline in `DIRECTION.md`) is **not used on this
surface** — nothing here is large/bold enough to safely spend it; the primary button uses the
verified `accent-ink` (`~7:1`) instead. The gradient CTA is likewise not used here — this
screen has no single hero action large enough to earn it.

## 10. Access

- `role="grid"` is **not** used here (cards/lanes, not a table) — the real `role="grid"` tables
  live one level down, inside each module.
- Every icon-only control (bell, tokens) carries a full accessible name naming state + record,
  never a color name alone — see §5/§6 examples.
- `44px` control floor everywhere a target is interactive (rail rows, header buttons, token hit
  areas). `8px` base unit throughout (gaps, padding all multiples of it).
- Skip link before the rail, one `h1` ("Home"), landmark `<main>` wraps the seven-lane grid.
- Focus ring `2px solid accent-ink`, `2px` offset, `:focus-visible` only, verified against
  `card` and against every token fill (§6).

## 11. Content direction

Buyer-role numbers are real-shaped (18 open POs, 6 low-stock items, 27 open sales orders) with
a comparison on every single one, quiet lanes (Finance/HR/Admin/Reporting) hold one calm token
each instead of sitting empty, and every identifier in a tooltip follows the terminology lock —
`item`, `vendor`, `warehouse`, `journal entry` — with no invented brand name, logo, or person.

---

**Self-check before return:** every hex above was read back against the palette table in
`DIRECTION.md §6` and the status-token table — no value was transcribed from memory. The two
nudged categorical hues (`Sales 66°`, `Admin 312°`) are logged with their reason and their new
clearance distance, not silently substituted.
