# the yard: Surface 6 of 7 — Empty State (Filtered)

Mode: **dark**. Canvas: fixed **1440×900** coded viewport (web/desktop-only, no platform mode).
Screen: Items list, filtered to zero results (`category = NON_STOCKED`, no matches).
Composition anchor: **centered-statement**. Background mode: **flat-surface**.

Same layout, region map, and 8px-unit numbers as the light spec — **one design, two
palettes**, per the concept's own rule. Only §3 (palette) and the one button-style note in
§1.7 differ; everything else below restates the geometry so this file stands alone.

---

## 1. Layout — region map (8px base unit throughout)

| Region | Bounds (x, y, w, h) | Notes |
|---|---|---|
| Left rail | 0, 0, 232, 900 | full height, `card` fill, 1px `hairline` right border |
| Title band | 232, 0, 1208, 64 | sticky, `card` fill |
| Filter-chips band | 232, 64, 1208, 56 | sticky (`space-sticky = 56px`), `card` fill, 1px `hairline` bottom border — present in this state, absent in true-empty (see §5) |
| Empty-state region | 232, 120, 1208, 780 | `substrate` fill, content centered |

Skip link, `#main-content`, `<nav aria-label="Primary">`: identical to the light spec.

### Left rail (232px)
- `0,0,232,64` — wordmark "Atlas", 14px/600, `text-primary`, padding-left 24px, vertically centered.
- Nav items, 44px height each: Home · **Inventory (active)** · Procurement · Sales · Finance · Reporting · Admin · — spacer — · Help (pinned last).
- Active state (Inventory): rail-item background `accent-tint-dark`, text `accent-dark`, 3px `accent-dark` left indicator bar.

### Title band
- h1 "Items" — 20px/600, `text-primary`, left-aligned, padding-left 32px. Unchanged by filter state.
- Secondary "+ New item" button, right-aligned 32px from edge, 44px height, 16px horizontal padding, `card` fill, 1px `hairline` border, radius 12px, 14px/500 `accent-dark` label.

### Filter-chips band (56px)
- Padding-left 32px. Meta label "Filters" — 12px/450 `text-secondary`.
- 12px gap, one chip: rounded-full pill, 44px height, 16px horizontal padding, `accent-tint-dark` fill, `accent-dark` text 14px/450: **"Category: Non-stocked"**, trailing 16px × glyph (`accent-dark`), 8px gap before it. `aria-label="Remove filter: Category — Non-stocked"`. `:focus-visible` ring: 2px solid `accent-dark`, 2px offset — matched to the dark run's own focus-ring reconciliation, checked against both `card` and the chip's own `accent-tint-dark` fill.

### Empty-state region (780px, centered-statement)
Same 480px-wide column, same vertical centering as the light spec.

1. **Dashed-outline token slot** — 96×96px, radius 24px, border 2px **dashed**, color
   `hairline` `oklch(0.34 0.015 290)`, fill transparent. Centered inside: static 28px
   outline "no-result" glyph (magnifier, diagonal slash), 2px stroke, `text-secondary`.
   Non-interactive, same rationale as light: the slot is decoration here, content in
   true-empty (§5).
2. Gap 24px.
3. h2 "No items match these filters." — 20px/600, `text-primary`, centered.
4. Gap 8px.
5. Body line — 14px/450, `text-secondary`, centered, max-width 400px: "Try removing a
   filter or broadening your search."
6. Gap 24px.
7. **"Clear filters" button** — 44px height, min-width 180px, 20px horizontal padding,
   radius 12px. **Style differs from light on purpose:** dark mode uses an **outline**
   button — transparent/`card` fill, 2px solid `accent-dark` border, 14px/600 `accent-dark`
   label — rather than a solid fill. Reason, read back against the palette table before
   writing this down: `accent-dark` at `L≈0.76` is a *light* color in dark mode; the
   palette table only verifies it as a foreground on `substrate`/`card` (~6:1), never as a
   fill with a white or dark foreground on top of it. Filling the button with `accent-dark`
   and setting a foreground on it would be an invented, unverified pairing — the exact
   mistake this gate exists to catch. An outline button sidesteps it entirely: it uses
   `accent-dark` only in the one role the table actually measured, as text/stroke on
   `card`/`substrate`. `aria-label="Clear filters — removes Category: Non-stocked"`.
   `:focus-visible` ring: 2px solid `accent-dark`, 2px offset, checked against `substrate`
   and against the button's own transparent interior so the ring never merges with the
   border.
8. Gap 8px, meta caption — 12px/450, `text-secondary`, centered: "Removes: Category =
   Non-stocked".

Live region (visually hidden, `role="status"`, `aria-live="polite"`): **"0 items match your
filters."**

---

## 2. Type table

| Level | Face | Size/weight | Line-height | Used for |
|---|---|---|---|---|
| Title | Inter Variable | 20px/600 | 28px (1.4) | h1 "Items"; h2 "No items match these filters." |
| Body/data | Inter Variable | 14px/450 | 20px (1.43) | rail labels, chip label, body line, secondary button label, "Clear filters" label |
| Meta | Inter Variable | 12px/450 | 16px (1.33) | "Filters" label, "Removes: …" caption |

---

## 3. Palette — paired, with measured ratios (from `DIRECTION.md` §6, dark table)

| Token | Value | Used for | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | empty-state region fill | text-primary | ~14:1 |
| card | `oklch(0.24 0.012 290)` | rail, title band, chips band | text-primary | ~13:1 |
| text-primary | `oklch(0.94 0.008 290)` | h1, h2, wordmark | — | — |
| text-secondary | `oklch(0.68 0.015 290)` | body line, meta caption, glyph, "Filters" label | on card | ~6:1 |
| hairline | `oklch(0.34 0.015 290)` | rail border, chips-band border, dashed slot outline, "+ New item" border | decorative-only, same caveat as light | — |
| accent-dark | `oklch(0.76 0.14 290)` | active-rail text/indicator, chip text, "+ New item" label, "Clear filters" border+text, focus ring | on substrate/card only — **never as a fill with a foreground on top, per §1.7** | ~6:1 |
| accent-tint-dark | `oklch(0.30 0.05 290)` | active-rail background, chip fill | accent-dark | ~5:1 |

`accent-emphasis`/gradient-CTA tokens are light-mode-only in `DIRECTION.md` §6 — no dark
equivalent is defined, and none is needed here since this screen's button stays on
`accent-dark` outline throughout.

---

## 4. Content direction (one line)

Identical copy to the light spec — one real filter, one plain explanation, one action that
names what it undoes — the dark palette retunes lightness/chroma only, never the words or
the structure.

---

## 5. True-empty comparison (documentation only, not this comp's render)

- **Chips band absent**, empty-state region runs `232,64,1208,836`.
- h1 stays **"Items"**.
- h2 reads **"No items yet — log the first one."**
- Dashed 96×96 slot **contains the primary action**: a 44px-min-height "+ Log item"
  control sized to the slot. In dark mode this stays the same **outline** treatment as
  "Clear filters" (2px `accent-dark` border, `accent-dark` 14px/600 label, transparent
  fill) for the identical reason given in §1.7 — no verified fill-with-foreground pairing
  exists for `accent-dark`, so true-empty's primary action does not get a heavier
  treatment than filtered-empty's in dark mode, even though light mode's true-empty could
  legitimately reach for a filled `accent-emphasis` button if its label were bumped to
  ≥16px/600 (see the light spec's §5 note). This is a stated light/dark asymmetry, not an
  oversight.
- Teaching line below the slot: 14px/450 `text-secondary`, **"Items you log here appear in
  this list, ready for procurement and stock counts."**
- No "Clear filters" action, no meta caption — nothing to clear.

Same structural mechanism as light: the slot is content (a button) in true-empty, decoration
(a static glyph) in filtered-empty.
