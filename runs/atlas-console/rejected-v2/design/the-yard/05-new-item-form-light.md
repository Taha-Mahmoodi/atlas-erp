# the yard: Surface 5 of 7 — New Item Form
### Palette: LIGHT · Platform: web/desktop-only · Canvas: 1440×900 (fixed coded viewport)

Fixes two confirmed live-app defects: (1) raw Pydantic/FastAPI error text dumped in one
top-of-form alert block, replaced with per-field, blur-triggered, plain-language, `status`
live-region messages; (2) operator input lost on validation error or failed save, replaced
with a persisted-field-state requirement (see `05-new-item-form.tokens.md` → "State model").

---

## 1. Layout — the numbers

**Composition anchor:** `stacked-center` — a single vertical run down the middle of the
canvas, space held either side. Deliberately calmer than surface 03 (items list, dense-grid)
and surface 04 (vendor bill detail, right-rail document-flow strip) either side of it in the
flow: no side rail of content, no grid, one column, generous white space.

**Background mode:** `flat-surface` — one solid substrate, the form card sits on it inline.
No gradient, no texture, no image. The calm is the point.

| Region | X | Y | W | H | Notes |
|---|---|---|---|---|---|
| Canvas | 0 | 0 | 1440 | 900 | substrate fill |
| Left rail (persistent nav) | 0 | 0 | 240 | 900 | rest state (icon+label), below 1600px breakpoint — no "today" badge reveal |
| Content area | 240 | 0 | 1200 | 900 | scroll container |
| Centered column | 520 | — | 640 | auto | `(1200 − 640) / 2 = 280` margin each side |
| Form card | 520 | 128 | 640 | auto | rounded, shadowed, see §3 |

**Left rail (240px, rest state):**
- Wordmark mark, 24px top padding, 32px height.
- Skip link, first focusable element, visually hidden until `:focus`, target `#main-content`.
- 11 module-lane nav items, role-derived order, most-frequent first. Each item: 44px control
  height (floor), 16px horizontal padding, icon 20px + label 14px/450, 4px icon–label gap,
  rounded-12 hover/active pill in the item's own categorical hue (`hue = 10 + index × 32`,
  chroma 0.11, L 0.60). Current context = **Inventory** lane active (item index 1 →
  `hue 42°`), shown as a filled rounded-12 pill behind that item only.
- Rail background: `card` token, 1px hairline right edge (decorative-only — paired with the
  240px width break and the content area's own shadow-free flat fill, never the sole
  boundary signal).

**Content column (640px), top to bottom:**
1. Breadcrumb — "Inventory / Items / New Item", meta scale, `text-secondary`, 8px
   margin-bottom.
2. `<h1>` "New Item" — title scale, `text-primary`, 4px margin-bottom. **The one h1 on this
   screen.**
3. Helper line — "Fields marked * are required." — meta scale, `text-secondary`,
   32px margin-bottom.
4. Form card — 640px wide, 40px padding (5 × 8 base unit), rounded-20, soft shadow (§3),
   `card` background.

**Inside the card — three groups, by mental model, 40px (5u) between groups:**

| Group | Fields | Required | Layout |
|---|---|---|---|
| **Identity** | Item name, SKU | both required | stacked, full 560px content width |
| **Stock** | Quantity, Reorder point, Warehouse | Quantity & Warehouse required; Reorder point optional | Quantity + Reorder point side by side, 272px each, 16px (2u) gap; Warehouse full-width below |
| **Sourcing** | Vendor | optional | full-width, with inline "+ Create vendor" affordance |

**Spacing scale used throughout (8px base unit):** 4 / 8 / 16 / 24 / 32 / 40px only. No
off-scale values.

**Control floor:** every input, select, combobox trigger, and button is **44px tall**,
never smaller.

**Field anatomy (top to bottom), every field identically:**
`label (above, always)` → 8px gap → `input, 44px` → 4px gap → `helper OR error slot`
(helper: meta scale, `text-secondary`, static; error slot: empty / collapsed to 0 height
until populated on blur, see `role="status"` note below).

**Card footer:** 24px padding above/below a 1px hairline divider (paired with the spacing
gap, not the sole signal), then a right-aligned row, 16px gap: **Cancel** (ghost/text
button, `text-secondary`) and **Create item** (primary, filled). Both 44px tall.

---

## 2. Type table

Scale locked to the four sizes this screen's brief specifies. No fifth size is introduced —
group headers and button labels reuse the 14px body/data slot at 600 weight rather than add
a new token.

| Role | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 26px | `<h1>` "New Item" only |
| Body/data | Inter Variable | 14px | 450 | 20px | field labels, input values, nav labels, breadcrumb-adjacent copy |
| Body/data (emphasis) | Inter Variable | 14px | 600 | 20px | group headers ("Identity" / "Stock" / "Sourcing"), button labels — same size slot, weight-bumped, not a new size |
| Meta/helper | Inter Variable | 12px | 450 | 16px | breadcrumb, helper text under fields, "optional" suffix, footer legal-weight copy |
| Inline error | Inter Variable | 12px | 500 | 16px | field-level validation message only |

**JetBrains Mono Variable: not used on this screen.** The concept reserves it for displayed
document identifiers (`BILL-2026-00003`-style codes on surfaces like 04). SKU here is an
operator-entered plain-text field on a form that has no finalized identifiers to display yet
— it renders in Inter Variable like every other input, per the brief's own note.

---

## 3. Palette — light, with ratios

| Token | Value | Role on this screen | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | canvas fill behind rail + content | text-primary | ~15:1 |
| card | `oklch(1 0 0)` | rail fill, form card fill | text-primary | ~16:1 |
| text-primary | `oklch(0.21 0.015 290)` | h1, field values, labels | on card/substrate | 15–16:1 (above) |
| text-secondary | `oklch(0.46 0.02 290)` | breadcrumb, helper text, Cancel button, "(optional)" suffix | on card | ~6.5:1 |
| hairline | `oklch(0.89 0.01 290)` | rail edge, field borders (1px), footer divider — decorative-only, paired with spacing, never the sole boundary signal | — | sub-3:1, non-text use only |
| accent-ink | `oklch(0.44 0.15 290)` | active-nav pill text, focus ring, "+ Create vendor" icon token, Inventory-lane accent | white / on card | ~7:1 (on card); **~6.5:1 on the pale error bg** (estimated — see below) |
| accent-emphasis | `oklch(0.53 0.18 290)` | **Create item** button fill | `oklch(1 0 0)` white label | **~4.8:1 — borderline, inherited RISK 4 from `DIRECTION.md` §5/§6, not independently re-verified here.** 14px/600 button label does not qualify as WCAG "large text," so this pairing clears the 4.5:1 floor only narrowly. Flagged, not silently altered — palette-level fix is out of this worker's scope. |
| accent-tint | `oklch(0.94 0.035 290)` | "+ Create vendor" row fill, newly-created-vendor "new" chip fill | accent-ink | ~6:1 |
| error text | `oklch(0.55 0.19 25)` | inline field-error message, error-token glyph | on error bg | ~5.5–6:1 (estimated) |
| error bg | `oklch(0.96 0.03 25)` | error-token fill, error-slot pill background | — | pale, per concept's Overdue/Error hue — never raw red |

**Focus ring:** 2px solid `accent-ink`, 2px offset, `:focus-visible` only. Checked against
both surfaces it will sit on: **card white** (~7:1, unambiguous) and **the pale error
background** `oklch(0.96 0.03 25)` (~6.5:1 estimated — both lightnesses sit near the top of
the range, so the ring loses little contrast moving from one to the other). Applies to every
input, select/combobox trigger, nav item, and button.

**All ratios above 4.5:1 are estimated by OKLCH/sRGB correspondence, not script-verified —
per `DIRECTION.md` §11, nothing in this package has rendered in a browser yet.**

---

## 4. Content direction

Copy stays operational and short: field labels name the exact ERP term (item name, SKU,
quantity, reorder point, warehouse, vendor — never product/sku/location/supplier), helper
text explains consequence not mechanism ("Flags Overdue when stock falls below this" under
Reorder point), and the only invented placeholder is a plausible SKU pattern
(`WHT-STL-014`) drawn from a generic hardware-stock domain — no brand name, no lorem, no
fabricated data presented as real.

**Shared, palette-agnostic interaction notes (validation timing, live-region wiring, the
persistence requirement, the inline vendor-create flow, Enter-submits) live once in
`05-new-item-form.tokens.md` rather than duplicated here and in the dark file.**

## 5. What I could not fully verify

The `accent-emphasis` / white pairing on the primary **Create item** button is inherited
from the concept palette at ~4.8:1 — borderline for 14px/600 text, already flagged upstream
as RISK 4. I did not soften or substitute it; it is reproduced as specified and re-flagged
here so it surfaces at Gate A rather than getting silently normalized.
