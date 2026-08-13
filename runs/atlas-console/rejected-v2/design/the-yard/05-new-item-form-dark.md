# the yard: Surface 5 of 7 — New Item Form
### Palette: DARK · Platform: web/desktop-only · Canvas: 1440×900 (fixed coded viewport)

Fixes two confirmed live-app defects: (1) raw Pydantic/FastAPI error text dumped in one
top-of-form alert block, replaced with per-field, blur-triggered, plain-language, `status`
live-region messages; (2) operator input lost on validation error or failed save, replaced
with a persisted-field-state requirement (see `05-new-item-form.tokens.md` → "State model").

One design in two palettes, not two art directions — the layout below is structurally
identical to the light file; only lightness/chroma retune.

---

## 1. Layout — the numbers

**Composition anchor:** `stacked-center` — a single vertical run down the middle of the
canvas, space held either side. Deliberately calmer than surface 03 (items list, dense-grid)
and surface 04 (vendor bill detail, right-rail document-flow strip) either side of it in the
flow: no side rail of content, no grid, one column, generous space.

**Background mode:** `flat-surface` — one solid substrate, the form card sits on it inline.
No gradient, no texture, no image.

| Region | X | Y | W | H | Notes |
|---|---|---|---|---|---|
| Canvas | 0 | 0 | 1440 | 900 | substrate fill |
| Left rail (persistent nav) | 0 | 0 | 240 | 900 | rest state (icon+label), below 1600px breakpoint |
| Content area | 240 | 0 | 1200 | 900 | scroll container |
| Centered column | 520 | — | 640 | auto | `(1200 − 640) / 2 = 280` margin each side |
| Form card | 520 | 128 | 640 | auto | rounded, shadowed, see §3 |

**Left rail (240px, rest state):** identical structure to the light file — wordmark, skip
link (`#main-content`), 11 role-ordered module-lane items at 44px control height, 20px icon
+ 14px/450 label, rounded-12 hover/active pill in the item's categorical hue
(`hue = 10 + index × 32`, chroma 0.11, **L 0.68 dark**). Current context = **Inventory**
lane active (`hue 42°`). Rail fill = `card` (dark) token, 1px hairline right edge
(decorative-only).

**Content column (640px):** breadcrumb (8px margin) → `<h1>` "New Item" (4px margin) →
helper line "Fields marked * are required." (32px margin) → form card (640px wide, 40px
padding, rounded-20, soft dark shadow, `card` dark background).

**Card groups — identical to light:** Identity (Item name, SKU, both required, stacked
full-width) → Stock (Quantity 272px + Reorder point 272px side by side, 16px gap; Warehouse
full-width below, required) → Sourcing (Vendor, optional, full-width, inline "+ Create
vendor"). 40px between groups.

**Spacing scale:** 4 / 8 / 16 / 24 / 32 / 40px only, same 8px base unit.

**Control floor:** every input, select, combobox trigger, and button is **44px tall**.

**Field anatomy:** `label (above, always)` → 8px gap → `input, 44px` → 4px gap → `helper OR
error slot` (error slot collapsed to 0 height until populated on blur).

**Card footer:** 24px padding above/below a 1px hairline divider, right-aligned row, 16px
gap: **Cancel** (ghost/text) and **Create item** (primary, filled), both 44px tall.

---

## 2. Type table

Same four-size scale as light — no palette-driven type changes. Dark mode changes color
only, never size or weight.

| Role | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 26px | `<h1>` "New Item" only |
| Body/data | Inter Variable | 14px | 450 | 20px | field labels, input values, nav labels, breadcrumb-adjacent copy |
| Body/data (emphasis) | Inter Variable | 14px | 600 | 20px | group headers, button labels — same size slot, weight-bumped |
| Meta/helper | Inter Variable | 12px | 450 | 16px | breadcrumb, helper text, "(optional)" suffix |
| Inline error | Inter Variable | 12px | 500 | 16px | field-level validation message only |

**JetBrains Mono Variable: not used on this screen** — same reasoning as light: reserved for
displayed document identifiers elsewhere in the flow, not this operator-entered SKU field.

---

## 3. Palette — dark, with ratios

| Token | Value | Role on this screen | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | canvas fill behind rail + content | text-primary | ~14:1 |
| card | `oklch(0.24 0.012 290)` | rail fill, form card fill | text-primary | ~13:1 |
| text-primary | `oklch(0.94 0.008 290)` | h1, field values, labels | on card/substrate | 13–14:1 (above) |
| text-secondary | `oklch(0.68 0.015 290)` | breadcrumb, helper text, Cancel button, "(optional)" suffix | on card | ~6:1 |
| hairline | `oklch(0.34 0.015 290)` | rail edge, field borders (1px), footer divider — decorative-only, paired with spacing | — | sub-3:1, non-text use only |
| accent-dark | `oklch(0.76 0.14 290)` | active-nav pill accent, focus ring, "+ Create vendor" icon token, **Create item** button fill (see note below) | on substrate/card | ~6:1 (as text/icon role, given) |
| accent-tint-dark | `oklch(0.30 0.05 290)` | "+ Create vendor" row fill, "new"-vendor chip fill | accent-dark | ~5:1 |
| error text | `oklch(0.65 0.17 25)` | inline field-error message, error-token glyph | on error bg | ~5:1 (estimated) |
| error bg | `oklch(0.28 0.05 25)` | error-token fill, error-slot pill background | — | dark-mode Overdue/Error hue, never raw red |

**Primary button pairing — a decision made here, flagged:** `DIRECTION.md`'s dark palette
states `accent-dark` only as a foreground/text role ("on substrate," ~6:1). It gives no
explicit dark-mode equivalent to light's `accent-emphasis` filled-button token. This spec
extends `accent-dark` to a **filled** button (bg `oklch(0.76 0.14 290)`) with a **dark**
label color (`oklch(0.19 0.012 290)`, the substrate-dark tone) rather than white, since
accent-dark is itself light (L 0.76) and needs a dark foreground to read — estimated
**~9:1**, comfortably clear, and notably not borderline the way light's equivalent pairing
is. Not lifted verbatim from the direction doc; re-verify at script-pass time along with
everything else in this package.

**Focus ring:** 2px solid `accent-dark`, 2px offset, `:focus-visible` only. Checked against
**card dark** `oklch(0.24 0.012 290)` (~8:1 estimated) and **the dark error background**
`oklch(0.28 0.05 25)` (~7:1 estimated) — both comfortable, since accent-dark's high
lightness (0.76) sits far from either dark surface. Dark mode's focus-ring contrast is the
more comfortable of the two palettes; light mode's is the tighter one.

**All ratios above are estimated by OKLCH/sRGB correspondence, not script-verified — per
`DIRECTION.md` §11, nothing in this package has rendered in a browser yet.**

---

## 4. Content direction

Same copy as light — content direction does not change between palettes. Field labels use
the exact ERP terms (item name, SKU, quantity, reorder point, warehouse, vendor), helper
text states consequence not mechanism, the only invented placeholder is the plausible SKU
pattern `WHT-STL-014` (generic hardware-stock domain, no brand, no lorem).

**Shared, palette-agnostic interaction notes (validation timing, live-region wiring, the
persistence requirement, the inline vendor-create flow, Enter-submits) live once in
`05-new-item-form.tokens.md`.**

## 5. What I could not fully verify

The dark primary-button pairing (§3 above) is my own extension of a palette that only
defines `accent-dark` as a foreground role, not a filled-button role — flagged rather than
presented as if `DIRECTION.md` stated it directly. All other ratios inherit the same
estimation caveat as the light file (§11 disclosure, unverified by script).
