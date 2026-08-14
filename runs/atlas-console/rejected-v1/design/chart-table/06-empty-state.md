# chart-table: Surface 6 of 7 — Empty state (filtered)

Concept: chart-table. Collision served: Swiss/International grid (structure) × editorial marginalia
(surface) — the grid supplies the axis and column discipline; the serif marginal note is the "hand
that checked it," sitting outside the grid in its own margin column, set at a slight angle like a
penciled correction.

Canvas: fixed desktop viewport spec, **1440×900**. Platform mode: N/A (web/desktop tool shell).

---

## Layout move

Persistent app chrome + a single centered "axis" as the empty-state device, instead of a dense
table with zero rows. This is deliberately the quietest surface in the set — no table grid is
drawn at all, only the one axis line the concept is named for, with everything else held back
from it.

**Chrome (unchanged across items-list / empty-state):**
- Left nav rail: `x 0–240`, full height `0–900`. 1px hairline right border (`hairline-border`,
  computed 1.31:1 against substrate — see note below). Nav items (Items / Vendors / Customers /
  Warehouses / Journal entries) stacked at `y 24, 64, 104, 144, 184`, each 40px row height,
  16px left inset from rail edge (`x=24`). "Items" is the active item: 2px accent-ink underline,
  full row width, sitting under the label.
- Top bar: `x 240–1440, y 0–64`. 1px hairline bottom border. Breadcrumb "Items" at `x=272, y=32`
  (vertically centered in the 64px bar), meta role.

**Content region:** `x 240–1440` (1200 wide) × `y 64–900` (836 tall). 12-column Swiss grid inside
it: 32px outer margin each side, 24px gutter, inner width `1200 − 64 = 1136`, column width
`(1136 − 11×24) / 12 = 872 / 12 ≈ 72.7px` (computed, not rendered).

**Header band**, `y 64–200` (136px):
- Page title "Items" — `x=272, y=104` baseline (40px below bar top), title role, 20px/600,
  primary-text.
- Filter chip row, `y=136–168` (32px band, 32px below title top):
  - Chip "Warehouse: East Loading Dock ✕" — pill, 1px hairline border, 16px radius, 6px/12px
    padding, `x=272`, width ≈214px (computed from ~190px of 14px/450 text + padding). Chip label
    set in body/data role (it reads as a field:value pair, tabular). The ✕ close control is a
    28×28px hit target with `:focus-visible` ring.
  - "Clear filters" text action — `x = 272 + 214 + 12 = 498`, same baseline as chip, meta role
    (12px/450), color accent-emphasis, **underlined** (not color-only — see contrast note),
    `:focus-visible` ring 2px solid accent-ink, 2px offset.

**Empty axis**, `y 200–780` (580px band), centered on content-region midline `x = (240+1440)/2 =
840`:
- Zero-value readout "0 results" — meta role, 12px/450, secondary-text, centered at `x=840,
  y=440`, tabular figures (echoes a chart's y-axis zero label rather than reading as prose).
- Axis line — 1px hairline, horizontal, `x 520–1160` (640px wide, centered on x=840), `y=480`.
- Day ticks — 6 short 1px hairline verticals, 8px tall, evenly spaced every 80px along the axis
  (`x = 560, 640, 720, 800, 880, 960, 1040, 1120`, 8 ticks total, computed not rendered).
- "Today" marker — the center tick at `x=840` only, rendered 2px wide × 12px tall in accent-ink
  (not hairline), with "Today" label directly below in meta role, secondary-text, `y=500`.
- No bars, no points, no plotted marks anywhere on the axis — that absence is the empty state.

**Marginal note**, right of the axis, outside the 12-column grid in a reserved annotation margin
`x 1184–1416` (232px wide, sits past the axis end at 1160 with a 24px gap):
- Copy: *"Nothing plotted for this filter. Clear it, or log the first item."* — margin-serif role,
  Source Serif 4 Variable, 13px italic/400, accent-ink. Set at `y=452` (roughly level with the
  axis line, slightly above), wraps to 3 lines at 232px width, rotated −1.5° to read as a
  penciled correction rather than typeset UI copy.
- Leader — 1px accent-ink elbow connector from the note's left edge to the "Today" tick at
  `x=1160→1184, y=480`, a proofreader's caret linking the annotation to the thing it annotates.

No table, no rows, no zebra striping is drawn on this surface — that is the point of the axis
device relative to `05-items-list`, which will carry the dense grid this state deliberately
withholds.

---

## Type table

| Role | Face | Size / weight | Line-height | Used for |
|---|---|---|---|---|
| Title | Inter Variable | 20px / 600 | 28px (1.4) | Page title "Items" |
| Margin serif | Source Serif 4 Variable, italic | 13px / 400 | 18px (1.38) | Marginalia note only |
| Body / data | Inter Variable, tabular-nums | 14px / 450 | 20px (1.43) | Filter chip label |
| Meta | Inter Variable | 12px / 450 | 16px (1.33) | Breadcrumb, "Clear filters", "0 results", "Today" label |

---

## Paired colors (OKLCH) with ratios

All ratios below are **computed, not rendered** — derived analytically (OKLCH → linear sRGB →
WCAG relative luminance → contrast ratio), not measured from a pixel output.

| Pair | Values | Ratio | Status |
|---|---|---|---|
| primary-text on substrate | `oklch(0.22 0.008 58)` on `oklch(0.99 0.002 58)` | **16.84:1** | computed, not rendered — well past AA/AAA |
| secondary-text on substrate | `oklch(0.46 0.01 58)` on `oklch(0.99 0.002 58)` | **6.94:1** | computed, not rendered — passes AA (4.5:1) with margin |
| accent-ink on substrate | `oklch(0.40 0.07 58)` on `oklch(0.99 0.002 58)` | **9.14:1** | computed, not rendered — meets the dispatch's "expect ≥7:1" |
| accent-emphasis on substrate | `oklch(0.58 0.10 58)` on `oklch(0.99 0.002 58)` | **4.29:1** | computed, not rendered — **short of the dispatch's "expect ≥4.5:1" by 0.21**, see below |
| hairline-border on substrate | `oklch(0.90 0.006 58)` on `oklch(0.99 0.002 58)` | **1.31:1** | computed, not rendered — non-text divider only, not a text pairing |
| accent-ink focus ring on substrate | `oklch(0.40 0.07 58)` | 2px solid, 2px offset | uses the 9.14:1 pair above |

**Contrast finding:** `accent-emphasis` on `substrate` computes to 4.29:1, not the ≥4.5:1 the
dispatch's palette note expects — it fails AA for normal-weight text at the 12px "Clear filters"
label. Mitigated in this comp by underlining the link (not color-only, satisfies 1.4.1) rather
than silently swapping the palette, since the palette pair is fixed by the dispatch, not mine to
redefine. Flagged below as unsatisfied rather than fixed unilaterally.

---

## Content direction

Copy is written for the filtered-empty case specifically, not generic empty-state boilerplate —
the chip stays visible so the cause is legible, the marginal note names the two real exits
("clear it, or log the first item") instead of a hollow "no results found," and "0 results" reads
as a chart's zero-value label rather than an apology.

---

## Composition anchor & background mode

- **Composition anchor: `stacked-center`.** A single vertical run — chip row, zero readout, axis,
  today marker — held on the content region's midline (`x=840`), with the margin note breaking
  off to the right as the one deliberately off-axis element. Quieter than `05-items-list`'s dense
  table by design: nothing competes with the axis for the eye.
- **Background mode: `flat-surface`.** One solid substrate throughout (`oklch(0.99 0.002 58)`),
  chrome and content both inline on it — no gradient, no image, no texture. The Swiss-grid side
  of the collision reads through flatness; the only "texture" in the frame is the hand-set angle
  on the marginal note.

One line: chosen because the surface's job here is to make a zero-result state legibly different
from a true-empty state at a glance — the visible chip plus the axis-with-a-gap does that without
adding a second heading or a stock empty-state illustration.

---

## Embarrassment-gate self-check

- Numbers re-read against the palette table above: pass — the two "expect" annotations in the
  dispatch were re-derived, not assumed, and the one miss (accent-emphasis) is called out rather
  than quietly rounded up.
- Grid math re-checked: content width 1200, inner width 1136, 12 cols at ~72.7px with 24px
  gutters and 32px margins sums correctly (72.7×12 + 24×11 + 32×2 = 872.4 + 264 + 64 ≈ 1200.4,
  within rounding).
- Terminology lock honored: "item," "warehouse" used; no "product," "SKU," or "location" crept
  in.
- Filtered-empty is distinct from true-empty: the chip stays on screen, copy names the filter as
  the cause, "Clear filters" sits adjacent to the chip per the dispatch's fix.
- Would a designer put their name on this: yes, with the accent-emphasis contrast miss disclosed
  rather than hidden — that is the finding a reviewer needs, not a reason to withhold the comp.

---

## Return

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/chart-table/06-empty-state.md`
- **Composition anchor:** `stacked-center`
- **Background mode:** `flat-surface`
- **One line:** Chose a single centered axis-with-a-gap over a dense zero-row table so the
  filtered-empty state reads as "nothing plotted here" rather than "the table broke" — quieter
  than the items-list surface, with the margin note doing the explaining instead of a second
  heading.
- **Unsatisfied:** `accent-emphasis` on `substrate` computes to 4.29:1, short of the dispatch's
  stated "expect ≥4.5:1" for the "Clear filters" label; mitigated with an underline rather than a
  palette substitution, but the ratio itself was not fixable within the given hexes. Also noting
  `hairline-border` on `substrate` is only 1.31:1 — fine as a decorative divider, but not strong
  enough to serve as a component boundary if a future pass needs the chip's outline to double as
  a required UI-boundary indicator (WCAG 1.4.11, 3:1 non-text).
