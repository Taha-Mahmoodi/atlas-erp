# gauge-house: Surface 3 of 7 — Items list

Canvas: fixed 1440×900 desktop viewport. Composition anchor: **`dense-grid`**. Background mode: **`flat-surface`**.

Terminology lock honored throughout: item / vendor / customer / warehouse / journal entry.

---

## 1. Layout move — exact numbers

**Vertical stack, 1440×900:**

| Band | Height | Contents |
|---|---:|---|
| Global header | 48px | Rail-adjacent wordmark, persistent ⌘K go-to, tenant name, user menu |
| Page header | 56px | `INVENTORY` eyebrow + `Items` title, row-count meta, `New item` action |
| Toolbar / filters | 40px | Type filter, warehouse filter, status filter, in-grid search — all at the 40px control-height floor |
| Grid sticky header | 48px | Column labels, reserved per spec, stays fixed while body scrolls |
| Grid body | 708px (remainder) | `900 − (48+56+40+48) = 708`. At 40px row height: `708 / 40 = 17.7` → **17 full rows + a 28px sliver of row 18** visible before scroll — lands inside the "~15–20 visible populated rows" target and the sliver is the scroll affordance, not a cut-off row |

**Left rail:** 64px fixed width, icon-only at rest, full 900px height. Not included in the 1376px content column below (`1440 − 64 = 1376`).

- Top: 48px tenant/logo mark (icon only)
- 13 module icons × 40px each = 520px (Home, Finance, Inventory *[active]*, Procurement, Sales, Manufacturing, Quality, Maintenance, HR, Projects, CRM, Reporting, Admin)
- Flexible spacer: `900 − 48 − 520 − 40 = 292px`
- Bottom-pinned: 40px settings/user icon

**Reveal-not-stretch nav interaction:** rail width never changes — 64px at rest, 64px on hover. On hover/focus of a single icon, a label pill reveals for *that icon only*: `position: absolute`, `left: 64px` (rail's right edge), top-aligned to the hovered icon's 40px row, height 40px, auto-width (label text + 12px horizontal padding each side), 1px hairline border + elevation shadow so it reads as floating over content rather than resizing the rail. Icon (18px) repeated inside the pill next to the label (14px/450). Content underneath never reflows.

**Content column (1376px, right of rail):** 32px page gutter each side → **1312px usable width** for the page header, toolbar, and grid.

**Grid columns, summing to 1312px:**

| Column | Width | Align | Notes |
|---|---:|---|---|
| Select | 40px | center | checkbox, `Space` selects |
| Item # | 132px | left | IBM Plex Mono Variable 13px/500 — fixed width, not flex, so codes stay vertically aligned |
| Name | 596px (flex) | left | Inter 14px/450 |
| Type | 96px | left | `STOCKED` / `SERVICE`, meta scale |
| Qty on hand | 96px | **right** | tabular-nums, decimal-aligned for non-discrete items (e.g. wire sold by the meter: `184.50`) |
| Warehouse | 120px | left | `WH-MAIN`, `WH-EAST`, `WH-ASSY`, `WH-QA` |
| Status | 112px | left | shape + label chip, never color alone |
| Row actions | 120px | right | icon cluster, see below |

Fixed columns sum to `40+132+96+96+120+112+120 = 716px`; Name takes the remainder: `1312 − 716 = 596px`.

**Row height: 40px floor, exact.** Text baseline centered: 14px/450 body text at 20px line-height leaves `(40−20)/2 = 10px` top/bottom padding per cell. Row divider: 1px hairline, full-bleed under each row. Header/body weight hierarchy (technical-drawing convention, major vs. minor line): **header bottom rule = 2px solid primary-text** `oklch(0.20 0.01 58)`; **row dividers = 1px hairline-border** `oklch(0.88 0.008 58)` — the heavier line marks the one structural boundary (header/body), the lighter line is a quiet minor gridline, never competing with it.

**Row-action icon cluster — the 24px spacing-exception geometry:**
- Two icon buttons per row: "Open ITM-BOLT" (detail), "More actions for ITM-BOLT" (overflow menu) — real accessible names, item code interpolated, never "Edit"
- Each hit-target: **24×24px** (documented exception to the 40px floor — desktop pointer-only admin grid, not a touch surface)
- Icon glyph: **18px**, centered in the 24px target (`(24−18)/2 = 3px` pad each side)
- Gap between the two hit-targets: **8px**
- Cluster total: `24 + 8 + 24 = 56px`, right-aligned in the 120px column with 16px inset from the table's right edge (`120 − 56 − 16 = 48px` left-side buffer from the Status column's divider)
- Focus ring on keyboard nav: 2px solid accent-ink, 2px offset, `:focus-visible` only

**Grid semantics:** `role="grid"`, `aria-rowcount`, `aria-colcount` on the container; each interactive cell is a `gridcell` with `tabindex="-1"` except the active one (roving tabindex). Arrow keys move focus cell-to-cell, `Enter` opens the row-action's primary target, `Space` toggles the select checkbox, `Shift`+arrow extends the selection.

---

## 2. Selected-row state — the certificate strip

Selecting a row (`Enter`, click, or `Space`+`Enter`) opens a **persistent** right-side panel — not an overlay, not a modal. It pushes the grid's live width, it does not float above it:

- Strip width: **360px**, full 900px height minus the same chrome bands above it (starts below the global header, at y=48)
- Grid area shrinks: `1312 − 360 = 952px` — Name column absorbs the loss (`596 − 360 = 236px`; Item #, Type, Qty, Warehouse, Status, actions stay fixed-width so the table stays legible under compression)
- Strip header: item code (mono-identifier, 13px/500) + name (body/data, 14px/450), 56px tall, 1px hairline border-bottom

**Content — vertical annotated timeline, this item's most recent replenishment chain (PO → GRN → Bill):**

Three certificate cards stacked with 16px gaps, connected by a vertical dimension-line rule (1px, dashed, accent-ink) with a small tick mark at each card's anchor point — this is where the blueprint surface treatment lives on this screen, confined to the 360px strip, never bleeding into the grid:

Each certificate card (blueprint-styled: hairline border, four corner registration ticks, 12px internal padding) carries exactly the four fields the collision sentence names:

| Field | Example | Type role |
|---|---|---|
| Document | `PO-4471` | mono-identifier, 13px/500 |
| Measured value | `Qty received: 480 EA` | body/data, 14px/450 tabular |
| Tolerance | `−20 EA vs. ordered (−4.0%)` | body/data, 14px/450 tabular, red text `oklch(0.5 0.18 25)` if outside tolerance, else secondary text |
| Checked by / date | `M. Reyes, Receiving · Aug 11` | meta, 12px/450 |

**Style-under-density is honored exactly as specified:** the grid stays hairlines-and-tabular-figures at all 17 visible rows — no per-row annotation, no card treatment leaking into the table. The certificate strip's blueprint ornament (corner ticks, dashed dimension line, calibration-card framing) exists only for the one selected row's chain, never for all 17 at once.

---

## 3. Type table

| Role | Face | Size | Weight | Line-height | Usage on this surface |
|---|---|---:|---:|---:|---|
| Screen title | Inter Variable | 20px | 600 | 28px (1.4) | "Items" |
| Section-eyebrow | Inter Variable | 12px | 600, caps, +0.06em tracking | 16px (1.33) | "INVENTORY", strip section labels |
| Body/data | Inter Variable | 14px | 450, tabular-nums where numeric | 20px (1.43) | Name, Type, Qty, Warehouse, toolbar controls, certificate values |
| Meta | Inter Variable | 12px | 450 | 16px (1.33) | Row-count text, timestamps, "checked by" lines |
| Mono-identifier | IBM Plex Mono Variable | 13px | 500 | 20px (1.54, matches body row rhythm) | Item # column, document codes in the certificate strip |
| Grid column header | Inter Variable | 12px | 600, caps, +0.06em tracking | 16px | Reuses section-eyebrow scale, 48px header band |

Inter Variable carries every proportional-text role for its tabular figures and wide weight range at this density; IBM Plex Mono Variable is scoped strictly to identifiers (`ITM-BOLT`, `PO-4471`) where fixed-width parsing beats Inter's proportional digits at a skim — both self-hosted, both load-bearing, neither swapped.

---

## 4. Paired colors, with ratios

Values taken directly from the dispatch are marked **(given)**. Everything else is a fresh computation done for this surface, run through an OKLCH→linear-sRGB→WCAG relative-luminance script and marked **(computed, not rendered)**.

| Pair | Foreground | Background | Ratio | Source |
|---|---|---|---:|---|
| Primary text / substrate | `oklch(0.20 0.01 58)` | `oklch(0.985 0.003 58)` | **17.35:1** | computed, not rendered |
| Secondary text / substrate | `oklch(0.45 0.012 58)` | `oklch(0.985 0.003 58)` | **7.14:1** | computed, not rendered |
| Accent-ink body/link text / substrate | `oklch(0.42 0.09 58)` | `oklch(0.985 0.003 58)` | **8.71:1 (given) / 8.34:1 (my recompute)** | given, re-verified — see flag below |
| White label / accent-emphasis button | `oklch(1 0 0)` | `oklch(0.55 0.13 58)` | **5.06:1** | given, re-verified — matches |
| Accent-ink text / accent-tint badge bg | `oklch(0.42 0.09 58)` | `oklch(0.94 0.03 58)` | **7.27:1 (given) / 7.26:1 (my recompute)** | given, re-verified — matches |
| Posted/Active chip text / bg | `oklch(0.5 0.12 150)` | `oklch(0.95 0.03 150)` | **4.95:1** | computed, not rendered — passes 4.5:1 body-text floor |
| Hairline border / substrate | `oklch(0.88 0.008 58)` | `oklch(0.985 0.003 58)` | **1.38:1** | computed, not rendered — see flag below |
| Dark mode: text / substrate | `oklch(0.94 0.006 58)` | `oklch(0.18 0.006 58)` | **15.77:1** | computed, not rendered |
| Dark mode: accent-dark / substrate | `oklch(0.72 0.10 58)` | `oklch(0.18 0.006 58)` | **7.40:1** | computed, not rendered — clears the ≥4.5:1 target stated in dispatch |

**Status chips actually used on this surface** (item master records realistically carry Active/Draft/discontinued states, not the Pending/Posted-workflow states that belong to documents — Pending and Posted/Active-as-workflow-state and Error/Overdue are not used here by domain logic, not by oversight):

- **Active** — the given green chip, `oklch(0.95 0.03 150)` bg / `oklch(0.5 0.12 150)` text, check glyph. Ratio above.
- **Draft** — neutral gray chip, dashed border, no exact value given in dispatch; proposed `oklch(0.93 0.006 58)` bg / `oklch(0.40 0.01 58)` text, **7.51:1 (computed, not rendered)**, built from the same neutral family as the substrate/text pair rather than a new hue.
- **Closed** (discontinued item, label only, no glyph) — no exact value given; proposed `oklch(0.32 0.008 58)` bg / `oklch(0.94 0.006 58)` text, **10.65:1 (computed, not rendered)**.

**Two flags from reading these numbers back:**

1. **Accent-ink on substrate:** dispatch states 8.71:1; my independent OKLCH→sRGB conversion gets 8.34:1. Both clear 4.5:1 by a wide margin so nothing on this surface is at risk, but the two numbers don't match exactly — likely a difference in gamut-clamping or rounding between whatever produced the dispatch figure and this script. Worth reconciling once, centrally, rather than per-surface.
2. **Hairline border vs. substrate measures 1.38:1** — well under the 3:1 WCAG non-text floor for a required UI boundary. On this surface that's likely fine: row dividers are a quiet minor gridline, not the only way to tell rows apart (40px height + text baseline already does that), and the *header* rule that actually needs to register as structure is 2px at 17.35:1. But it means the row hairlines are decorative, not accessibility-load-bearing, and that should be a stated decision, not an assumption.

---

## 5. Content direction

One line: populate the grid with real manufacturing-domain item codes in the existing `ITM-XXXX` convention (bolts, castings, gaskets, sensors — not lorem, not five rows of "Sample Item"), mixed Active/Draft/Closed status realistically weighted toward Active, and skip inventing a money/unit-cost column since the dispatch's column list for this surface didn't call for one — the decimal-alignment requirement is honored through the Qty-on-hand column instead.

---

## Composition anchor & background mode

- **Composition anchor:** `dense-grid` — the 17-row table is the majority of the canvas by area and by attention; the rail, header, and toolbar are all subordinate chrome sized to their functional minimum, never competing with the table for weight.
- **Background mode:** `flat-surface` — one solid substrate `oklch(0.985 0.003 58)`, every asset sits inline on it. No texture, no gradient, no image anywhere in the base surface — that flatness is what makes the certificate strip's blueprint ornament (dashed dimension line, corner registration ticks) read as a deliberate, confined exception rather than one texture among several.

**One line on the pick:** this surface is the run's density proof, so the anchor had to be the grid itself, not a framing device around it — `dense-grid` over `left-rail-caption` or `right-rail-caption` because neither of those would let 17 real rows read as the primary content at a glance; `flat-surface` keeps the "technical drawing is flat and authoritative" half of the collision true everywhere except the one place (the certificate strip) where the style-under-density line says ornament is allowed to live.

## What I couldn't fully satisfy

- **Draft and Closed chip colors are my own extrapolation**, not values handed down in the dispatch (which only specified Active, Pending, and Error/Overdue exactly). I built them from the existing neutral family for internal consistency and computed their ratios, but they need sign-off as canonical, not just accepted because they're plausible.
- **The hairline-border/substrate ratio (1.38:1) doesn't clear the 3:1 non-text UI-boundary floor.** Flagged above rather than quietly reinterpreted — if row dividers ever need to carry meaning on their own (not just alongside row height), the value needs raising.
- **The 8.71:1 vs. 8.34:1 accent-ink discrepancy** between the dispatch's stated ratio and my independent recomputation is small and doesn't change any pass/fail outcome here, but it's a palette-table detail worth reconciling once centrally rather than re-flagging on every surface that touches accent-ink.
