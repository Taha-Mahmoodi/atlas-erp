# lightbox: Surface 6 of 7 — Empty State (Filtered)

**Mode:** dark · **Canvas:** 1440×900 (fixed coded viewport, web/desktop-only) · **Composition
anchor:** `centered-statement` · **Background mode:** `flat-surface`

This comp renders the **filtered-empty** variant: the Items list after an applied filter
combination returns zero rows. The live app currently renders this identically to the
true-empty (brand-new, unfiltered) state — a confirmed defect. The fix is structural, not
cosmetic: the active-filter chip row below is the tell, and it is **only ever present** on the
filtered variant. See "True-empty variant, for comparison" at the bottom for the unfiltered
copy and the one layout difference.

Job of this screen: tell the operator instantly *why* the list is empty (their own filters,
not a broken system) and hand them the one action that resolves it, without adding a single
decorative element to the plainest register in the set. Same design as the light file — only
color retunes, per the concept's "one design in two palettes" rule; layout numbers below are
identical to `06-empty-state-light.md`.

## Layout — numbers

Base unit: 8px. Control floor: 44px. Substrate fills the full 1440×900 canvas, `substrate`
fill, no texture, no image — nothing is inline on it except the two chrome regions and the
content column below, hence `flat-surface`.

**Left rail** — `x:0–240, y:0–900`, flat, opaque, `substrate` fill, `1px solid hairline` right
edge (decorative only — the boundary signal is the column gap and the content's own left
padding, not this line). Icon+label module nav, no blur, no glass. Nav list starts at `y:88`
(clears the floating bar below), each item a 44px-tall row, 16px left padding, 20px icon +
8px gap + 14px/500 label. "Items" is the active entry: `row-alt` fill behind that one row only,
text-primary weight, no color change — active state is a fill+weight shift, never a hue shift,
consistent with the concept's "no token pills" discipline.

**Glass command bar** — the one glass object on the entire screen, per the concept's
collision. Fixed, floating: `top:16px, left:16px, right:16px` → `1408×56px`, `18px`
border-radius. Fill `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)`,
`backdrop-filter: blur(20px)`, border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290)
75%)` — dark mode runs less opaque and reads through more than light's 60% mix, per the
concept's stated art-direction split, declared not inverted-naively. Left to right, 16px outer
padding, 8px gaps: 24×24 brand glyph + "Atlas" wordmark (15px/600) → search field, flex-grow,
placeholder "Search or press / to jump" (14px/500, command-bar-label style, on its own text
scrim) → quick-create icon-button `44×44px` (`+`, `aria-label="Quick create"`) →
notifications icon-button `44×44px` (bell, `aria-label="Notifications"`). Every text run on
this bar sits on its own scrim (re-measured for dark, same rule as light), flagged for
build-time re-measurement against the busiest scrolling row, not assumed passing. Item
creation lives here (quick-create), not duplicated as a second button in the content header
below.

**Content column** — `x:280–1400` (1120px wide) inside the content area `x:240–1440,
y:88–900`. Top padding to clear the bar: content starts at `y:88`, then 32px inset to `y:120`.

1. **h1 "Items"** — `y:120`, 20px/600, `text-primary`. Unchanged from the normal (populated)
   list state — this state never rewrites the screen title.
2. Gap 16px → `y:164`: **active-filter chip row**, `role="list" aria-label="Active filters"`,
   flex row, 8px gap between chips, left-aligned. Three example chips: "Vendor: Acme Metals",
   "Warehouse: North DC", "Status: Draft" — each `28px` tall, `6px 10px` padding, `8px`
   border-radius, `1px solid hairline` border (decorative only — the real boundary signal is
   the discrete `row-alt` fill block plus the dismiss glyph, not the hairline alone, same
   caveat as the concept's own hairline note), `row-alt` fill, text 12px/450 `text-primary`,
   trailing 12px "×" dismiss glyph inside a `20×20` visual target sitting inside a real `44×44`
   click/tap zone (padding absorbs the difference — the chip's own row height stays 28px).
   Each dismiss removes one filter and re-queries; **this row is present if, and only if,
   filters are active** — it is the structural marker that separates this state from
   true-empty.
3. Gap 20px → `y:212`: **table header row** (`role="row"` inside `role="grid"`), `40px` tall,
   bottom `1px solid hairline` (decorative only — the real column-boundary signal is text
   alignment and the header/body type-weight contrast, not this line). Five columns across
   the 1120px column: Item (360px) · Vendor (220px) · Warehouse (180px) · Status (160px) ·
   Updated (200px). Header labels 12px/450 `text-secondary`, left-aligned except Updated
   (right-aligned, matches tabular data below it).
4. **Body region** — `y:252–860` (608px tall; 40px bottom padding held before the canvas
   edge). No rows render. Centered within this region, both axes: vertical center `y:556`,
   horizontal center `x:840` (the content column's own midpoint, not the full canvas —
   keeps the message aligned under the grid it replaces, not floating mid-screen).

**The empty message — one flat line, nothing else.** No card, no shape, no icon, no color
beyond the two text tokens below:

> No items match these filters. Clear filters

Single line, 14px/450. "No items match these filters." in `text-primary`. One word-space, then
"Clear filters" in `accent-dark`, no underline at rest, underline on `:hover`/`:focus-visible`.
It reads and sits inline within the sentence — not a button, not a chip, not offset onto its
own visual row. Clicking/tapping it clears every active filter chip above and re-queries the
grid.

**Target-size decision (stated, not defaulted):** "Clear filters" is genuinely inline text
within a running sentence on one line — the WCAG 2.5.8 *inline exception* applies directly (a
target that is part of a sentence or block of text is exempt from the minimum target-size
rule), and there is no adjacent interactive target within 24px to create a spacing conflict.
No enlarged hit box is added around it, and none is required; the honest small target is the
correct choice here precisely because it keeps the line looking like one sentence, not a
button wearing text as a disguise — which is what "reads as plain text-link, not a button"
means structurally, not just visually.

**Live-region announcement** (separate from the visible copy above, `role="status"
aria-live="polite"`, visually hidden `sr-only`): `"0 items match your filters."` — fires once,
when the result count settles at zero after a filter change. It does not duplicate the visible
sentence; it exists so a screen-reader user gets an immediate, terse announcement without
waiting to navigate to the visible line.

**Skip link:** first in DOM/tab order, before the rail and the bar. Visually hidden until
`:focus-visible`, then `top:16px; left:16px`, `accent-dark` background, `substrate`-dark text
(inverted for contrast on the light-accent chip), 14px/600, `8px 16px` padding, `8px` radius,
above everything including the glass bar. Copy: "Skip to items list" — targets the h1.

**Focus ring** (skip link, rail nav items, bar's search/quick-create/notification controls,
each chip's dismiss glyph, "Clear filters"): `2px solid accent-dark`, `2px` offset,
`:focus-visible` only.

**One h1 on the page:** "Items." The empty-state sentence is a `<p>`, not a heading.

## Type

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| Wordmark (bar) | Inter Variable | 15px | 600 | 20px |
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / data / empty-message line | Inter Variable | 14px | 450 | 20px |
| Command-bar label | Inter Variable | 14px | 500 | 20px |
| Meta / table header / chip text | Inter Variable | 12px | 450 | 16px |

No JetBrains Mono here — no document identifier renders on a zero-row grid.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas, rail, content | substrate | `oklch(0.155 0.01 290)` | text-primary | ~15:1 |
| Chip fill, active-nav-row fill | row-alt | `oklch(0.205 0.012 290)` | text-primary | ~13:1 |
| Table header, chip text, footer meta | text-secondary | `oklch(0.70 0.014 290)` | on substrate | ~6:1 |
| Rail border, chip border, table header rule | hairline | `oklch(0.33 0.014 290)` | — decorative only, same caveat as the concept's own note |
| "Clear filters" link, focus ring, skip-link bg | accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 |
| Glass command bar fill | glass panel (dark) | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `blur(20px)` | text via inner scrim | flagged for build-time re-measurement (RISK 1) |

All ratios above are estimated from OKLCH/sRGB correspondence, not script-verified — carried
forward from `DIRECTION.md` §11's disclosure, not re-derived here.

## Content direction

Terminology lock honored: "vendor" and "warehouse" appear in the example filter chips, never
"supplier." The empty-message copy is the concept's own stated line, unmodified: "No items
match these filters." + "Clear filters" — no invented brand claim, no lorem, no fabricated
totals (deliberately no "0 of N items" count anywhere on this screen — a specific number here
would be a fabricated data claim per the run's own guardrail, not a plausible structural
placeholder).

## True-empty (unfiltered) variant — for comparison, not rendered here

Same canvas, same chrome, same h1, same table-header row. Two differences only, and they are
the whole fix for the live defect:

1. **No filter-chip row.** Step 2 above is entirely absent — there is nothing to have
   filtered, so nothing renders there. Its absence is itself the signal that distinguishes
   this from the filtered-empty state; a build that shows an empty chip-row container here
   instead of omitting the row reproduces the bug in a new shape.
2. **Different one-line message**, same position (`y:556`, same 14px/450, same inline-link
   treatment, same WCAG 2.5.8 inline-exception reasoning):

   > Nothing logged yet. Log the first item

   "Nothing logged yet." in `text-primary`, "Log the first item" in `accent-dark`, same
   underline-on-hover/focus behavior. This is the very first thing a brand-new tenant's first
   user sees on this screen — it has to teach, not just report, so its link points at record
   creation (opens the new-item form, surface 05) rather than at clearing anything.
