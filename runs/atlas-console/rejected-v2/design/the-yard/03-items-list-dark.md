# the yard: Surface 3 of 7 — Items List

Mode: **dark**. Canvas: fixed **1440×900** coded viewport (web/desktop-only, no platform
mode). Screen: Inventory > Items, unfiltered, full dataset. Composition anchor:
**dense-grid**. Background mode: **flat-surface**.

Same screen, same job, same layout math as `03-items-list-light.md` — this is "one design
in two palettes," per `DIRECTION.md` §6, not a second art direction. Only color retunes;
region bounds, column widths, row math, and the interaction contract are identical and not
re-derived here. This file states the dark-specific values and anything dark mode changes
structurally (mainly: text-on-accent inverts, since `accent-dark` is a light color).

---

## 1. Layout — region map (identical to light; 8px base unit throughout)

| Region | Bounds (x, y, w, h) | Notes |
|---|---|---|
| Left rail | 0, 0, 232, 900 | full height, `card` fill, 1px `hairline` right border |
| Title band | 232, 0, 1208, 64 | sticky, `card` fill |
| Filter/search band | 232, 64, 1208, 56 | sticky (`space-sticky = 56px`), `card` fill, 1px `hairline` bottom border |
| Table card | 264, 120, 1144, 724 | inset 32px both edges, rounded-16, shadowed — see §5 |
| Footer/pagination band | 232, 844, 1208, 56 | `card` fill, 1px `hairline` top border |

Sums unchanged: `64+56+724+56=900`; rail `232` + content `1208` = `1440`; table card inner
width `1144` = sum of the 8 column widths in §5.

Skip link: visually hidden, first in tab order, reveals on `:focus` at `(16,16)`; targets
`#main-content`. One `<main id="main-content">`, one `<nav aria-label="Primary">`, one `<h1>`
("Items") — same landmark structure as light.

---

## 2. Left rail (232px)

- `0,0,232,64` — wordmark "Atlas," `14px/600`, `text-primary` `oklch(0.94 0.008 290)`,
  padding-left `24px`.
- Nav items, `44px` height, `20px` icon + `8px` gap + `14px/450` label: Home ·
  **Inventory (active)** · Procurement · Sales · Finance · Reporting · Admin · — spacer —
  · Help (pinned last).
- Active state (Inventory): rail-item background `accent-tint-dark` `oklch(0.30 0.05 290)`,
  text `accent-dark` `oklch(0.76 0.14 290)`, `3px` `accent-dark` left indicator bar.
- Focus ring: `2px solid accent-dark`, `2px` offset, `:focus-visible` only.

---

## 3. Title band (1208×64px)

- `<h1>` "Items" — `title` 20px/600, `text-primary`, padding-left `32px`.
- Breadcrumb "Inventory / Items" — `meta` 12px/450, `text-secondary` `oklch(0.68 0.015 290)`.
- Right, `32px` from the edge, `16px` gap:
  - **Density toggle** — icon-only, `44×44px` hit target, "Toggle row density," same rule
    as light: compact mode never drops row height below `40px`; this comp renders the
    default `48px` row.
  - **"+ New item"** — primary button, `44px` height, `16px` horizontal padding, radius
    `12px`, fill `accent-dark` `oklch(0.76 0.14 290)`, label `14px/600` in **substrate-dark
    text** `oklch(0.19 0.012 290)` — inverted from light's white-on-accent-ink, because
    `accent-dark` is itself a light color (`L 0.76`); dark text on it, not light text, is
    what clears contrast. Same inversion pattern surface 02's dark file uses for its own
    primary button, applied here rather than re-derived.

---

## 4. Filter/search band (1208×56px, sticky)

Padding-left/right `32px`, `12px` gaps:

1. **Search field** — `320×44px`, `card` fill `oklch(0.24 0.012 290)`, `1px hairline`
   border, radius `10px`, placeholder "Search items by name or SKU" (`text-secondary`).
2. Meta label "Filters" — `12px/450`, `text-secondary`.
3. **One example chip**: rounded-full pill, `44px` height, `16px` horizontal padding,
   `accent-tint-dark` fill, `accent-dark` text `14px/450`: **"Vendor: Acme Fastening Co."**,
   trailing `16px` × glyph (`accent-dark`), `8px` gap before it.
   `aria-label="Remove filter: Vendor — Acme Fastening Co."`. Focus ring: `2px solid
   accent-dark`, `2px` offset.
4. "+ Add filter" — ghost text button, `14px/450` `accent-dark`.

Same caveat as light: this chip illustrates the control; the 38-row table below is the
unfiltered dataset, shown to prove density. Filter state lives in the URL query string per
`TOOLS.md` — no visual signature, noted per the dispatch's instruction.

---

## 5. Table card (1144×724px, rounded-16)

Fill `card` `oklch(0.24 0.012 290)` on `substrate` `oklch(0.19 0.012 290)`. Shadow (dark
needs a stronger read against a dark ground than the light formula, per surface 02's dark
file — same values reused, not re-derived): `0 1px 2px oklch(0 0 0 / 0.3), 0 8px 24px
oklch(0 0 0 / 0.35)`. `overflow: hidden`, radius `16px`.

**Sticky header** — `56px`, `position: sticky; top: 0`, rounded top corners. Column labels
`meta (emphasis) 12px/600`, `text-secondary`, uppercase, letter-spacing `0.04em`. Sortable:
Item, Category, Qty on hand, Reorder point, Vendor.

**Column widths — identical to light (sum 1144px):**

| Column | Width | Align | Content |
|---|---|---|---|
| Select | 40px | center | row checkbox |
| Item | 320px | left | item name (14px/450) over SKU (13px/500 mono), 2px gap |
| Category | 150px | left | body/data 14px/450 |
| Qty on hand | 110px | right | body/data 14px/450, `tabular-nums` |
| Reorder point | 120px | right | body/data 14px/450, `tabular-nums` |
| Vendor | 210px | left | body/data 14px/450 |
| Status | 90px | center | signal-token |
| Actions | 104px | right | 3-icon cluster |

**Row anatomy** — `48px` height, same math as light: `4+20+2+18+4=48`.

**Row divider signal — paired**, same rule as light, dark values: rows zebra between `card`
`oklch(0.24 0.012 290)` (even) and `substrate` `oklch(0.19 0.012 290)` (odd) — a larger,
more visible ~5% L delta than light mode's, plus a `1px hairline` `oklch(0.34 0.015 290)`
bottom border on every row (still paired, never the sole signal). Hover: row fill →
`accent-tint-dark`. Focused cell: `2px solid accent-dark` ring, `2px` offset, inside the
cell.

**Status column** — the exact same `28×28px` token component from surface 02 §6, unmodified
(dark pairs below), `44×44px` hit target, hover-reveal tooltip = `aria-label`. `90px`
column, no WCAG 2.5.8 exception needed (same reasoning as light §5 — only Actions needs it).

Status-token vocabulary, dark pairs:

| State | Fill | Text/glyph | Glyph |
|---|---|---|---|
| Draft | `oklch(0.3 0.01 290)` | `oklch(0.85 0.01 290)` | dashed ring, pencil |
| Active | `oklch(0.68 0.14 150)` | `oklch(0.16 0.02 150)` | check |
| Low-stock | `oklch(0.7 0.13 80)` | `oklch(0.18 0.02 80)` | clock |
| Discontinued | `oklch(0.65 0.17 25)` | `oklch(0.16 0.02 25)` | exclaim |
| Archived | `oklch(0.5 0.01 290)` | white | lock |

Accessible-name pattern unchanged from light (same three worked examples, same 38-row
repeat): `"Low-stock — Item ITM-BOLT-M8X25, 86 on hand, reorder point 150."` etc.

---

## 6. `role="grid"` interaction contract

Identical to light §7 — the interaction model is not a visual property and doesn't retune
between palettes: `39×8` grid, roving `tabindex`, Arrow/Home/End navigation, Enter opens the
right-side detail panel (Item/Category/Qty/Reorder/Vendor cells) or enters widget-editing
(Status cell: `220×236px` popover, `card` fill, `1px hairline` border, radius `12px`, dark
shadow from §5; Actions cell: cycles the 3 buttons), Escape restores grid navigation without
committing, Space toggles row selection from any cell, Shift+Arrow/Click extends the
selection range to a contextual action bar ("Change status," "Export"). Row-removed-by-edit
focus rule unchanged (`ACCESS.md` row 13).

---

## 7. Row actions (visible on focus, not hover-only)

Same `104px` cluster, same three controls (**Open** eye / **Edit** pencil / **More** ⋯),
same WCAG 2.5.8 spacing math: `18px` glyph in a `24×24px` region, `8px` gaps, `24px`
centre-to-centre. Same visibility rule: opacity `0` at rest, `100%` on `tr:hover` or
`tr:focus-within`, always in the DOM/tab order regardless of visual opacity. Icon color
`text-secondary` at rest, `accent-dark` on hover/focus. Same accessible-name pattern:
`"Open ITM-BOLT-M6X20"` / `"Edit ITM-BOLT-M6X20"` / `"More actions for ITM-BOLT-M6X20"`.

---

## 8. Footer/pagination band (1208×56px)

Left: "Showing 1–38 of 214 items" (`body` 14px/450, `text-secondary` — illustrative, not a
claimed metric). Right: **Prev** (disabled)/**Next**, `44px` height, `card` fill, `1px
hairline` border, radius `12px`, `14px/500` `accent-dark` label. Cursor-paginated, page size
`40`.

---

## 9. Data — the same 38-row dataset

Identical rows to light (same items, same qty/reorder/vendor/status values — inventory data
doesn't change by color scheme). See `03-items-list-light.md` §9 for the full table rather
than duplicating 38 rows byte-for-byte in both files; the palette section above (§5) is
this file's only content-bearing addition, since the dataset itself is palette-agnostic.

Status distribution (unchanged): `17` Active, `11` Low-stock, `4` Draft, `3` Discontinued,
`3` Archived. `13` rows visible before scroll at `48px` row height in the `668px` scrollable
body; all `38` documented, not a 5-row token sample.

---

## 10. Type table

Identical to light — type does not retune between palettes.

| Level | Face | Size/weight | Line-height | Used for |
|---|---|---|---|---|
| Title | Inter Variable | 20px/600 | 28px (1.4) | `<h1>` "Items" |
| Body/data | Inter Variable, tabular | 14px/450 | 20px (1.43) | item name, category, vendor, footer text, chip label |
| Meta | Inter Variable | 12px/450 | 16px (1.33) | breadcrumb, "Filters" label |
| Meta (emphasis) | Inter Variable | 12px/600 | 16px (1.33) | column headers |
| Mono-identifier | JetBrains Mono Variable | 13px/500 | 18px (1.38) | SKU codes |

Qty on hand / Reorder point: Inter `tabular-nums`, right-aligned — unchanged.

---

## 11. Palette — dark, with ratios

| Token | Value | Used for | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | page fill, odd-row zebra tint, "+ New item" label | text-primary | ~14:1 |
| card | `oklch(0.24 0.012 290)` | rail, title band, filter band, table card, even-row zebra tint | text-primary | ~13:1 |
| text-primary | `oklch(0.94 0.008 290)` | h1, item names, wordmark | — | — |
| text-secondary | `oklch(0.68 0.015 290)` | breadcrumb, meta labels, footer text | on card | ~6:1 |
| hairline | `oklch(0.34 0.015 290)` | rail border, band borders, row bottom border | decorative-only, paired with zebra tint | same caveat as light |
| accent-dark | `oklch(0.76 0.14 290)` | active-rail text/bar, "+ New item" fill, chip text, focus ring, popover selection | on substrate/card | ~6:1 |
| accent-tint-dark | `oklch(0.30 0.05 290)` | active-rail bg, chip fill, row hover fill | accent-dark | ~5:1 |

No `accent-emphasis` equivalent is defined for dark in `DIRECTION.md` §6, and none is needed
— `accent-dark` (`~6:1`, verified) already covers every accent use on this screen, same as
surface 02's dark file concludes for its own primary button.

All ratios estimated by OKLCH/sRGB correspondence, not script-verified — per `DIRECTION.md`
§11.

---

## 12. Style-under-density claim

Identical claim and identical proof to light §12 — the Status column's `90px`/`28×28px`
token footprint doesn't change between palettes, only its fill and text hues do. Forty rows
still cost nothing extra.

---

## 13. Content direction

Same domain, same 38 items, same terminology lock (**item**, **vendor**) as light — content
does not retune between palettes any more than layout does.

---

**Self-check before return:** every dark hex above was read back against `DIRECTION.md` §6's
dark palette table and dark status-token vocabulary — no value carried over from light by
assumption. The text-on-`accent-dark` inversion (substrate-dark text, not white) was checked
against surface 02's dark file rather than guessed, since `accent-dark`'s own lightness
(`0.76`) makes white-on-it the wrong direction.
