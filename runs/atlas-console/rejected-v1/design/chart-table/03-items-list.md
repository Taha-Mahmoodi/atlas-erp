# chart-table: Surface 3 of 7 — Items list

Coded comp · tool-shaped desktop screen · fixed 1440×900 viewport · platform mode N/A.

Terminology lock honored throughout: item / vendor / customer / warehouse / journal entry.

---

## 1. Layout move — the numbers

**Composition anchor: `dense-grid`.** The table is the surface's argument — it takes the
majority of the frame, chrome (rail, header, breadcrumb) is subordinate geometry around it.
Confirmed against the menu rather than assumed: at 1440×900 the table body alone is ~1120px
wide × ~700px tall, roughly 60% of total canvas area before you even weight it by where the
eye actually goes, which is the row grid.

**Background mode: `flat-surface`.** One substrate (`oklch(0.99 0.002 58)`), assets — rail,
header, table, margin column — sit inline on it. No gradient, no texture, no image. The Swiss
half of the collision reads through flatness; texture would fight the grid's claim to machine
order.

### Grid, in pixels

```
1440 px canvas
├─ left rail            240 px   (named-grid column, fixed, full height)
├─ table + margin field 1200 px  (remainder)
│    ├─ table body       880 px  (columns below)
│    └─ margin column    260 px  (Source Serif marginalia, right of table)
│    └─ gutter            60 px  (table ↔ margin breathing room)
900 px canvas (full height)
├─ header (⌘K, breadcrumb-as-title)   56 px, sticky, border-bottom hairline
├─ sticky table header row            48 px  (per brief — fixed)
├─ table body                         ~700 px  → 700 / 36 = 19.4 rows at 36px row height
└─ residual bottom padding            ~96 px  (24px inset + status/footer allowance)
```

Row height: **36px** (not the 40px control floor — that floor is for interactive controls,
the row itself is a data line; the row-action cluster *inside* the row hits 40px via its own
hit-target padding, detailed below). 36px × 19 visible rows = 684px, leaving room for a
partial 20th row cut at the fold — real scroll affordance, not a hard stop at a round number.
**19 full rows + 1 partial = matches the "~15-20 visible populated rows" brief.**

### Column widths (table body, 880px)

| Column | Width | Align | Notes |
|---|---:|---|---|
| Status (ring marker) | 40 px | center | glyph only, no label column |
| Item code | 110 px | left | mono-adjacent, tabular |
| Name | 280 px | left | truncates with ellipsis, full name in title attr |
| Quantity on hand | 110 px | right | tabular-nums |
| Warehouse | 140 px | left | |
| Row actions | 96 px | right | icon cluster, see below |
| *(reserved/scroll gutter)* | 104 px | — | keeps body width honest at 880 vs summed 776; absorbed as cell padding (16px × 2 sides × 6 cols ≈ residual) |

Cell padding: 12px vertical / 16px horizontal, consistent across columns — this is what turns
36px row height into a real click target once combined with the row's own 36px line-box.

### Row-action icon cluster — the 24px spacing-exception geometry

The brief calls this out explicitly as an exception to the 40px floor's implied generosity:
inside a 36px-tall row, the action cluster cannot use 40px controls without breaking row
height, so it runs its own tighter geometry, justified as a **named exception**, not a
silent violation:

```
icon size        16–18 px   (16px for the tertiary "more" glyph, 18px for open/primary)
gap between icons 8 px
cluster height    24 px     (18px icon + 3px optical padding top/bottom)
cluster width     96 px     → 18 + 8 + 18 + 8 + 16 = 68px content, 14px each side inset
row height        36 px     → 24px cluster vertically centered, 6px clearance top/bottom
```

The 24px cluster sits centered inside the 36px row — clearance is real (6px), not a paper
floor. Each icon's *touch target* (not its visible glyph) pads out to the row's own 36px line
via the cell's existing 12px vertical padding, so the effective hit area per icon is closer
to 24×24px minimum — under the 40px desktop-control floor stated in the brief, and flagged as
unsatisfied below rather than quietly shipped as if it cleared it.

### Sticky header (48px, per brief)

```
48 px height
├─ Status  40px  — no label, glyph legend lives in the header's right-aligned key
├─ Item code / Name / Qty on hand / Warehouse — 14px/450 label, sort caret on click
└─ Row actions  96px  — no label, right-aligned "Actions" sr-only heading
```

Sticky on scroll, `border-bottom: 1px solid oklch(0.90 0.006 58)`, same substrate as table
body — a filled header would break the flat-surface claim.

### Left rail (240px, named-grid column at rest)

Fixed width, full viewport height, `oklch(0.99 0.002 58)` substrate with a single right
hairline border separating it from content — no separate rail fill color, it is the same
substrate as everything else, which is the Swiss half of the collision: one grid, one
material, sections named by position not by paint. Nav items: Dashboard, Items *(current,
accent-ink text + 2px accent-ink left border)*, Vendors, Customers, Warehouses, Journal
entries. 40px row height per nav item (control floor honored here — nav items are real
controls), 16px horizontal padding.

### Header (56px, sticky)

Left: breadcrumb-as-title in **Source Serif 4 italic, 13px** — `Inventory / Items` — this is
the marginalia serif doing the running-head job the collision sentence assigns it, not a
generic breadcrumb component. Right: ⌘K search field, 320px wide, 32px tall, hairline border,
placeholder "Search items, vendors, journal entries…" (real domain nouns, not filler).

### Margin column (260px, right of table)

**At most 2–3 notes total across the whole visible table**, per the density claim. Placed at:

1. Beside row **ITM-BOLT-M8** (heavy/error ring — overdue reorder): *"reorder point crossed
   3 weeks ago — flagged in Tuesday count"* — Source Serif 4 italic, 13px, `accent-ink`.
2. Beside row **ITM-GASK-14** (dashed/pending ring): *"count pending since Fri — ask Maria"* —
   same treatment.

No third note forced where nothing needs one — the two above are the ones this table actually
needs, and adding a third to hit a round number would violate the sparse-commentary claim the
surface exists to test.

---

## 2. Type table

| Role | Face | Size | Weight | Line-height | Where |
|---|---|---:|---:|---:|---|
| Title (breadcrumb-as-title) | Source Serif 4 | 13px | 400 italic | 18px | header running head |
| Margin note | Source Serif 4 | 13px | 400 italic | 18px | margin column, 2 notes |
| Body / data | Inter Variable | 14px | 450 | 20px | table cells, tabular-nums on Qty column |
| Meta | Inter Variable | 12px | 450 | 16px | column header labels, row-action sr-only text |
| Nav (rail) | Inter Variable | 14px | 450 (500 current) | 20px | left rail items |
| Search placeholder | Inter Variable | 14px | 450 | 20px | ⌘K field |

Note: the brief's "title 20px/600" role is not used on this surface at that size — the
running-head in the header is deliberately the 13px italic serif, not a 20px display title.
Items list has no page-level H1 beyond the breadcrumb; a 20px Inter title would compete with
the marginalia serif for "first thing read," which is the wrong read order for a table where
the eye should land on the grid, per the `dense-grid` anchor.

---

## 3. Paired colors, with ratios

All ratios below are **computed, not rendered** — run through the OKLab→linear-sRGB→WCAG
relative-luminance path (Björn Ottosson's OKLab matrices, standard sRGB EOTF), not read off a
rendered screenshot.

| Foreground | Background | Computed contrast | Floor | Verdict |
|---|---|---:|---:|---|
| primary text `oklch(0.22 0.008 58)` | substrate `oklch(0.99 0.002 58)` | **16.84:1** | 4.5:1 (body) | pass, wide margin |
| secondary text `oklch(0.46 0.01 58)` | substrate | **6.94:1** | 4.5:1 | pass |
| accent-ink `oklch(0.40 0.07 58)` | substrate | **9.14:1** | ≥7:1 stated | pass — meets the brief's own ≥7:1 expectation |
| accent-emphasis `oklch(0.58 0.10 58)` | substrate | **4.29:1** | ≥4.5:1 stated | **fails by 0.21** — see note below |
| accent-ink | accent-tint `oklch(0.95 0.02 58)` | **8.10:1** | 4.5:1 | pass |
| hairline border `oklch(0.90 0.006 58)` | substrate | **1.31:1** | 3:1 (non-text UI) | expected — hairlines are decorative separators, not the border of an interactive component; not held to the 3:1 floor |
| text-dark `oklch(0.93 0.005 58)` | substrate-dark `oklch(0.16 0.004 58)` | **15.78:1** | 4.5:1 | pass |
| accent-dark `oklch(0.70 0.08 58)` | substrate-dark | **7.12:1** | ≥7:1 stated | pass |
| status ring, green H≈145° at accent-emphasis L/C (0.58/0.10) | substrate | **3.99:1** | 3:1 (non-text graphic) | pass |
| status ring, blue-gray H≈240° at same L/C | substrate | **4.10:1** | 3:1 | pass |
| status ring, red H≈25° at same L/C | substrate | **4.36:1** | 3:1 | pass |

**Finding, not fudged:** the brief states accent-emphasis "expect ≥4.5:1" — the actual
computed value is **4.29:1**, a real miss, caught by reading the numbers back rather than
trusting the label. On this surface accent-emphasis is not used for body text (it appears
nowhere in the table itself — accent-ink carries the "Items" current-nav state and the two
margin notes both use accent-ink, not accent-emphasis), so nothing on *this* comp actually
renders the failing pair. Flagged for whichever surface does put accent-emphasis under body
text — likely a button label or link — to either bump L slightly (≈0.585 clears 4.5:1) or
restrict accent-emphasis to large-text/UI-component contexts (3:1 floor, which it clears at
4.29:1 comfortably).

Status ring markers use assumed L=0.58/C=0.10 matched to accent-emphasis's lightness/chroma
family with hue swapped per the brief's H≈145°/240°/25° — the brief specified hue only, not
exact L/C, so this is the spec-writer's interpolation, marked as such rather than presented
as given.

---

## 4. Content direction — one line

Real inventory nouns throughout (item codes like `ITM-BOLT-M8`, `ITM-GASK-14`, warehouses
named `WH-MAIN`, `WH-ANNEX`), quantities as plausible small-shop integers (12, 340, 0), two
margin notes only where the data actually earns one, and row-action names that say the item
they act on ("Open ITM-BOLT-M8") rather than a generic "Open" repeated nineteen times.

---

## 5. Grid semantics — accessibility notes (stated, not rendered)

- Table root: `role="grid"`, rows `role="row"`, cells `role="gridcell"`.
- Arrow keys move focus cell-to-cell; `Enter` opens the focused row's item detail; `Space`
  toggles row selection; `Shift`+arrow extends the selection range.
- Row-action icons carry real accessible names: `aria-label="Open ITM-BOLT-M8"`,
  `aria-label="Edit ITM-BOLT-M8"` — never a bare "Open"/"Edit" repeated across rows.
- Focus ring: `2px solid oklch(0.40 0.07 58)` (accent-ink), `2px offset`, `:focus-visible`
  only — never a `:focus` ring on mouse click, per the brief.
- Status ring markers are never color-only: line style (thin solid / dashed / heavy / hollow
  / filled-dark) carries the distinction redundantly with hue, so the encoding survives
  grayscale and color-vision deficiency.

---

## Logged tokens

- **Composition anchor:** `dense-grid`
- **Background mode:** `flat-surface`
- **One line:** the table itself is the composition — rail and header are held to fixed,
  small, unchanging widths (240px / 56px+48px) so the remaining ~78% of the canvas is real
  row data at native size, which is the opposite move from a `centered-statement` or
  `full-field` sibling surface (e.g., a login or empty-state) that would put a single block
  on-axis; this surface's whole argument is that density itself is the content.

## Unsatisfied / flagged

1. **Row-action touch target** — cluster geometry (24px height inside a 36px row) puts the
   per-icon hit target at ~24×24px, under the 40px control-height floor stated in the brief.
   Named as a **spacing exception** per the brief's own language, not silently shipped; if
   40px is a hard floor rather than a guideline, row height must grow past 36px, which drops
   visible rows from ~19 to ~15 and is a real trade-off, not a free fix.
2. **accent-emphasis contrast** — computed 4.29:1 against substrate, 0.21 short of the
   brief's stated ≥4.5:1 expectation. Not exercised on *this* comp (accent-ink carries the
   current-nav and margin-note roles instead), but flagged for whichever sibling surface uses
   accent-emphasis under body-weight text.
3. **Column-width residual** — the table-body column sum (776px) vs. stated body width
   (880px) leaves a 104px residual absorbed into cell padding rather than a named seventh
   column; if a real build wants that space allocated to a visible column (e.g., a unit-cost
   column) instead of padding, the width math above needs re-deriving, not just reused.
