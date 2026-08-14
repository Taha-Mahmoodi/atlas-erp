# press-panel: Surface 3 of 7 — Items list

**Surface:** 03-items-list · **Concept:** press-panel (data-brutalist × claymorphism, gated on restraint)
**Canvas:** fixed 1440×900 viewport spec · **Platform mode:** N/A (desktop web app shell)
**Terminology lock:** item / vendor / customer / warehouse / journal entry

**Purpose:** the daily-grind dense table. Inventory Items, 17 populated rows visible in-viewport
(184 total, scroll implied), proving two things at once: the density claim (forty rows is this
system's designed load, and this surface renders 17 of them at full data density without a
single soft shadow in the body) and the two-role restraint (the only dimensional object on
17 rows of data plus a header full of controls is one status pill on two of those rows).

---

## Composition anchor + background mode (logged)

- **Composition anchor: `dense-grid`** — the table is 756px of this 900px canvas's vertical
  space (84%). Rail and page header are subordinate framing, not competing focal points.
- **Background mode: `flat-surface`** — one solid substrate (`oklch(0.98 0.002 58)`) under
  everything. No gradient, no image, no texture. The only non-flat objects in the entire
  frame are the two clay elements described below; their shadows are the sole visual event
  breaking the flat field, which is the point of the concept.
- **One line:** dense-grid + flat-surface is the plainest possible reading of "instrument
  panel" — I did not reach for a gradient or a duotone to make a table look interesting; the
  restraint is the composition, and the one pressable clay object is what the eye finds
  precisely because nothing else on the canvas is trying to compete with it.

---

## Layout move, with numbers

### Grid (1440×900)

| Zone | X | Width | Y | Height |
|---|---|---|---|---|
| Nav rail (rest) | 0 | 64px | 0 | 900px (full bleed) |
| Nav rail (hover/focus flyout) | 0 | 200px, **overlay** — does not reflow main content | 0 | 900px |
| Main content | 64 | 1376px | 0 | 900px |
| Page header | 64 | 1376px | 0 | 96px (56px title/search/CTA row + 40px toolbar row) |
| Table sticky header | 64 | 1376px | 96 | 48px (reserved, per spec) |
| Table body (viewport) | 64 | 1376px | 144 | 756px |

Table body: 756px ÷ 44px row height = 17.18 → **17 fully visible rows + an 8px sliver of
row 18**, which is the scroll affordance, not a rendering error. 17 populated rows sits
inside the ~15–20 target and is the number that actually proves the density claim: this is a
working screen at working density, not a hero shot with six rows of air.

### Nav rail

- Width at rest: **64px**, full height, background substrate (no separate rail color — flat
  system, one substrate throughout, rail separated from content only by a 1px hairline at
  x=64).
- Icons: 24px glyph inside a **40px** square hit target (control-height floor honored even
  for icon-only controls), stacked with **8px** gaps, 12px top padding before the first icon.
- 6 rail items: Home, **Items (active)**, Vendors, Customers, Warehouses, Journal entries —
  plus Settings pinned to the bottom with 12px bottom padding.
- Active state (Items): flat left-edge indicator bar, 3px wide, full 40px height, fill
  `accent-ink`; icon glyph recolors to `accent-ink`; 4px-radius background wash behind the
  icon in `accent-tint`. No shadow, no elevation — active state is flat, same as everything
  else on the rail.
- Hover/focus reveal: rail expands to **200px** as an absolutely-positioned overlay (box-
  shadow `0 4px 16px oklch(0.19 0.006 58 / 0.12)` on the flyout edge only — this is ordinary
  UI elevation for an overlay panel, not the clay treatment, and it is the one place a shadow
  appears outside the two clay roles; it is a panel casting a shadow onto the page beneath
  it, not a rendered surface pretending to be pressable). Label text appears at 14px/450,
  16px left of the icon. Main content column stays fixed at 1376px regardless of rail state.

### Page header (96px)

Row 1 (56px), y=0–56:
- Title "Inventory Items" — 20px/600, x=24 from content edge (x=88 absolute), vertically
  centered.
- ⌘K search field — 320px wide, 40px tall, x centered-right of title with 24px gutter,
  flat: 1px `hairline` border, 8px radius, placeholder "Search items, vendors, warehouses…"
  at 14px/450 in `secondary-text`, right-aligned "⌘K" hint chip inside the field (11px/450,
  `secondary-text`, no border).
- **Primary CTA "New item"** — the one clay button. 40px tall, auto-width (20px horizontal
  padding around 14px/600 label), right-aligned, 24px from content's right edge (x=1416
  absolute). See clay spec below.

Row 2 (40px), y=56–96, flat toolbar:
- Item count: "184 items" — 12px/450, `secondary-text`, left-aligned.
- Filter chips (flat, 24px tall, 6px radius, 1px hairline border, 8px horizontal padding):
  "All warehouses", "All statuses" — 8px gap between chips.
- View/density toggle, right-aligned — flat icon buttons, 32px hit target, 6px radius,
  ghost (no border at rest, `accent-tint` fill on hover).

### Table — columns (table width 1328px = 1376 − 24px inset each side)

7 columns, 16px gutter between each (6 gutters × 16px = 96px), fixed + one fill column:

| Column | Width | Align | Notes |
|---|---|---|---|
| Select (checkbox) | 40px | center | flat checkbox, 4px radius, 40px hit target |
| Item code | 128px | left | 14px/450 tabular, e.g. `ITM-BOLT-014` |
| Name | **560px (fill)** | left | 14px/450, e.g. "Hex Bolt M8×40, Zinc" |
| Qty on hand | 96px | right | 14px/450 **tabular-nums**, e.g. `1,240` |
| Warehouse | 144px | left | 14px/450, e.g. `WH-East-02` |
| Status | 168px | left | flat chip, or the one clay pill on pending rows |
| Row actions | 96px | right | icon cluster, see geometry below — ALL FLAT |

Sum check: 40+128+560+96+144+168+96 = 1232 + 96 (gutters) = **1328px** ✓ matches table width.

- Row height: **44px** (clears the 40px control-height floor with 4px to spare for text
  breathing room; tabular-nums keeps every numeric row perfectly rank-aligned).
- Row divider: 1px `hairline` border, bottom edge only, full-bleed across the row.
- Row hover: flat `accent-tint` background wash, no shadow, no lift, no border change.
- Selected row: flat `accent-tint` background (same token as hover, distinguished by a 3px
  left-edge `accent-ink` bar, same visual language as the rail's active indicator — the
  system reuses one flat "selected" language everywhere instead of inventing a second one).
- Grid semantics: `role="grid"` on the table, `role="row"`/`role="gridcell"` on children.
  Arrow keys move cell focus, `Enter` opens the row's item detail, `Space` toggles row
  selection, `Shift`+arrow extends the selection range. Focus on any cell — including a
  status cell holding the clay pill — renders the same **2px solid `accent-ink` hard ring**,
  2px offset, no blur. The ring does not change shape or softness for the clay cell; the
  restraint rule applies to fill and shadow, not to focus treatment.

### Row-action icon cluster — the 24px spacing-exception geometry

Sits inside the 96px action column, right-aligned, **entirely flat**:

- 3 ghost icon buttons per row: **Open**, **Edit**, **More** (kebab → duplicate/archive).
- Icon glyph size: **18px** (within the specified 16–18px range).
- Gap between icons: **8px**.
- Cluster content width: 3×18 + 2×8 = **70px**.
- Gap from the cluster to the Status column boundary: **24px** — this is the stated
  spacing-exception: every other horizontal gutter in this table is 16px, but the action
  cluster gets a wider 24px buffer so it reads as a distinct control zone, not a fourth data
  column crowding the status chip.
- Icon buttons at rest: no border, no fill, `secondary-text` glyph color. Hover: 6px-radius
  `accent-tint` fill behind the 18px glyph, glyph recolors to `primary-text`. No shadow at
  any state — this is the row the restraint rule is tested on, and it holds flat through
  rest, hover, and focus.
- Accessible names, per item, e.g. row `ITM-BOLT-014`: `aria-label="Open ITM-BOLT-014"`,
  `aria-label="Edit ITM-BOLT-014"`, `aria-label="More actions for ITM-BOLT-014"`.

### Status chips — flat (draft / posted / error / closed)

24px tall, 6px radius (deliberately tight — full/stadium radius is reserved for the clay
pill only; every flat shape in this system uses 4–6px radii so shape itself signals which
objects are pressable), 8px horizontal padding, 6px gap between glyph and label:

- **Draft** — dashed 1px neutral border (`hairline`), no fill, label-only, `secondary-text`.
- **Posted** — check glyph + "Posted" label, `oklch(0.50 0.14 145)` (green H≈145°, computed
  for this spec to extend the palette's L/C pattern to the posted hue — not in the dispatch
  palette verbatim, flagged below), on `oklch(0.95 0.03 145)` tint fill.
- **Error / Overdue** — exclaim glyph + "Error" or "Overdue" label, `oklch(0.50 0.16 25)`
  (red H≈25°, same extension logic) on `oklch(0.95 0.035 25)` tint fill.
- **Closed** — label-only, no border, no fill, `primary-text`, slightly denser weight (600)
  to read as final/settled rather than empty like draft.

Shape+label always carries the state — color is never the only signal, per spec.

### The one clay pill — "Pending" (exact dimensions)

Appears in the Status column on pending/in-progress rows only (2 of the 17 visible rows in
this sample, e.g. a stock-count-in-progress item and an item mid-transfer):

- Height: **28px**. Radius: **20px** (full stadium — the only stadium shape anywhere on this
  surface). Horizontal padding: **14px**. Auto-width, hugs content.
- Fill: `accent-emphasis` `oklch(0.60 0.14 58)`.
- Label: "Pending" — **13px/600**, color `primary-text` (see contrast note below).
- Glyph: small clock/spinner-dash icon, 14px, left of label, 6px gap.
- Shadow pair (embossed, single fixed light source from **top**):
  - Highlight: `inset 0 1px 0 oklch(0.98 0.002 58 / 0.55)` — top inner edge only.
  - Near shadow: `0 1px 2px oklch(0.19 0.006 58 / 0.18)`.
  - Far shadow: `0 4px 8px oklch(0.19 0.006 58 / 0.14)`.
  - Same three-value shadow recipe is reused, scaled, on the CTA button below — one light
    source, one shadow language, two applications, system-wide.
- Focus (when the cell holding it receives grid focus): 2px solid `accent-ink` ring, 2px
  offset, hard edge, no blur — added on top of the clay shadows, not replacing them.
- Nowhere else on this surface does `accent-emphasis` appear — not on hover, not on a
  filter chip, not on the toolbar. This is the literal proof point for "reserved... nowhere
  else": one hex, one role, one surface-wide instance count that does not grow with row count.

### The other clay role — primary CTA "New item" (exact dimensions)

- Height: **40px**. Radius: **12px** (rounded rect, not stadium — deliberately differentiated
  from the pill so the two clay objects don't read as one repeated shape).
- Horizontal padding: **20px**. Label: 14px/600.
- Fill: `accent-ink` `oklch(0.40 0.10 58)`. Label color: `substrate` `oklch(0.98 0.002 58)`.
- Same shadow-pair recipe as the pill (highlight top inner edge, near + far shadow below),
  scaled up slightly for the larger surface: near shadow `0 2px 3px`, far shadow `0 6px
  12px`, same opacities and light direction.
- Focus: identical 2px solid `accent-ink` hard ring, 2px offset.
- This is the second and last instance of claymorphism system-wide. Table rows, row-action
  icons, filter chips, rail icons, the search field, every flat chip — none of them get this
  treatment at any row count, which is the density claim: cost of the clay system is two
  fixed objects, not a function of 17 rows or 184.

---

## Type table

| Role | Face | Size | Weight | Line-height | Numeric | Used for |
|---|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 24px | — | Page title "Inventory Items" |
| Body/data | Inter Variable | 14px | 450 | 20px | tabular-nums on Qty column | Table cells, search field, rail labels |
| Meta | Inter Variable | 12px | 450 | 16px | — | Item count, chip micro-labels |
| Clay-pill label | Inter Variable | 13px | 600 | 16px | — | "Pending" pill only |

No second typeface anywhere on the surface, per spec.

---

## Paired colors, with ratios (computed OKLCH→sRGB, not rendered)

Converted OKLCH→linear sRGB→sRGB (Björn Ottosson's OKLab matrices) then WCAG relative-
luminance contrast. Hexes below are the computed sRGB output of the dispatch's OKLCH values,
not eyeballed:

| Token | OKLCH | Computed hex |
|---|---|---|
| substrate | `oklch(0.98 0.002 58)` | `#f9f8f7` |
| primary-text | `oklch(0.19 0.006 58)` | `#161311` |
| secondary-text | `oklch(0.44 0.008 58)` | `#56514e` |
| hairline | `oklch(0.86 0.005 58)` | `#d4d0ce` |
| accent-ink | `oklch(0.40 0.10 58)` | `#6e3700` |
| accent-emphasis (clay) | `oklch(0.60 0.14 58)` | `#bc670c` |
| accent-tint | `oklch(0.93 0.035 58)` | `#fbe3d2` |

| Pair | Ratio | Reads as |
|---|---|---|
| primary-text on substrate | **17.44:1** | body/title text, way past AA |
| secondary-text on substrate | **7.34:1** | meta text, passes AA on small text |
| accent-ink on substrate | **8.97:1** | rail active icon, links |
| substrate on accent-ink (CTA label on CTA fill) | **8.97:1** | passes comfortably |
| primary-text on accent-tint | **14.94:1** | text on hover/selected wash |
| accent-ink on accent-tint | **7.68:1** | active rail icon on its own wash |
| hairline on substrate | **1.45:1** | correct for a divider — not a text pair |
| **primary-text on accent-emphasis (pill label)** | **4.48:1** | **flagged below — marginal** |
| substrate on accent-emphasis | 3.89:1 | fails as body text; not used as such |
| accent-ink on accent-emphasis | 2.31:1 | fails; not used — glyph is primary-text, not accent-ink |

**Flag:** the clay pill's label at `primary-text` on `accent-emphasis` computes to **4.48:1**,
0.02 under the 4.5:1 AA threshold for normal text. 13px/600 does not clear WCAG's "bold large
text" exemption (needs ≥18.66px at 700, this is neither). It passes AA for non-text/UI-
component contrast (3:1) and is one rounding step from passing as text, but I'm not rounding
it away — see "unsatisfied" below. The other status-chip hues (posted-green, error-red at
`oklch(0.50 …)` / `oklch(0.95 …)`) are extensions I computed to match the dispatch palette's
L/C pattern at the stated hue angles (H≈145°, H≈25°); the dispatch gave hue angles, not full
OKLCH triples, for those two, so I'm flagging that as an assumption, not a given.

---

## Content direction (one line)

Row content is real inventory shape, not filler: alphanumeric item codes (`ITM-BOLT-014`,
`ITM-GASK-102`), plausible mechanical/hardware names at real length ("Hex Bolt M8×40, Zinc"),
four-digit-and-under quantities, three real-looking warehouse codes, and only 2 of 17 rows
carrying the clay pending pill — the ratio itself is the content decision, because a items
list where half the rows are "pending" would undercut the restraint claim before the layout
even had a chance to.

---

## Embarrassment-gate self-check

- Palette hexes read back against the table above: substrate/primary-text/secondary-text/
  hairline/accent-ink/accent-emphasis/accent-tint all match their OKLCH source — checked.
- Claymorphism instance count on this surface: **exactly 2** (CTA button, pending pill on 2
  of 17 rows). Zero on table rows, zero on row-action icons, zero on filter chips, zero on
  the rail's overlay shadow (that shadow is ordinary panel elevation, not the clay recipe —
  different shadow values, no highlight/near/far three-part structure, no embossed fill).
  Checked against the restraint rule directly.
- Four bands: N/A — desktop tool-shaped surface, not mobile; the equivalent (sticky table
  header reserved at 48px, rail reserved at 64px, no edge-to-edge content) is honored.
- Row height (44px) ≥ 40px control floor: checked. Row-action icon hit targets are visually
  18px glyphs without a stated 40px individual hit box — flagged below, this is the one place
  the surface doesn't cleanly clear the floor by design.
- Collision readable: a flat, dense, 17-row instrument panel where the only object with a
  shadow is one button and (on 2 rows) one pill — nothing else asks the hand to press it.
- Would a designer put their name on this: yes, with the pill-contrast number named honestly
  rather than smoothed over.

---

## Returned

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/press-panel/03-items-list.md`
- **Composition anchor:** `dense-grid`
- **Background mode:** `flat-surface`
- **One line:** dense-grid + flat-surface, because the table itself (17 rows, real columns,
  tabular-nums) is the whole argument, and the one clay pill only reads as an event because
  the 17 rows around it, and the header around that, refuse to compete with it.
- **Unsatisfied:**
  1. Clay-pill label contrast (`primary-text` on `accent-emphasis`) computes to 4.48:1,
     0.02 under AA-normal-text 4.5:1 — passes AA for UI components (3:1), fails for text by a
     hair. Two fixes that don't touch the locked OKLCH values: bump the label to 14px, or
     accept it as a UI-component contrast case (it's a status indicator, not body copy) — I
     did not silently round this to "passes."
  2. Row-action icon cluster (18px glyph, no stated 40px hit box) sits below the 40px
     control-height floor as an individual target, by the dispatch's own explicit exception
     for this 24px cluster geometry. Mitigated by full keyboard grid nav (arrow/Enter/Space)
     not depending on pointer precision, but flagging it since the floor is stated
     system-wide elsewhere and this is a named exception, not a default.
  3. Posted-green and error-red OKLCH triples aren't in the dispatch palette — only hue
     angles are (H≈145°, H≈25°). I computed plausible L/C extensions matching the existing
     tint/ink pattern; these should be confirmed against whatever the other 6 surfaces land
     on for the same two states, since I can't see their specs.
