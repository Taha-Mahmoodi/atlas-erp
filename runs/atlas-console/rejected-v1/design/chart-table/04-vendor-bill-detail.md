# chart-table: Surface 4 of 7 — Vendor bill detail

Coded-comp mode. Canvas: tool-shaped desktop screen, 1440×900 fixed viewport, full chrome. Platform mode: N/A (web).

**Surface job, one sentence:** let an AP clerk confirm BILL-2026-00003 is correct *and* see, without leaving the screen, that the bill's position in the Purchase Order → Goods Receipt → Vendor Bill chain was hand-checked — including the one place it deviated from plan.

## Logged tokens

- **Composition anchor:** `right-rail-caption`
- **Background mode:** `flat-surface`
- **One line:** Wide left field carries the bill itself — header fields, line-item table, totals — as the loudest thing on the canvas; the narrow right rail demotes the PO→GR→Bill lifecycle chain to inspector/metadata status, so the grid never has to compete with its own margin note. Differs from siblings 03 (items-list) and 06 (empty-state), which are both `dense-grid`/`full-field` respectively per the dispatch brief — this is the one surface in the set where a secondary column of content is load-bearing, which is what justifies breaking from the grid-only anchor.

## Canvas grid — numbers

```
Canvas                 1440 × 900
Global top bar          1440 ×  64   y:0–64      (kept from shell, shared w/ siblings 01–07)
Left nav rail            224 × 836   x:0–224,  y:64–900  (kept from shell)
Content area             1216 × 836  x:224–1440, y:64–900
  Content padding        32px all sides
  Inner content box      1152 × 772  x:256–1408, y:96–868

Right-rail-caption split (inner content box, 1152 wide):
  Main field    768px   x:256–1024
  Gutter         32px   x:1024–1056
  Right rail    352px   x:1056–1408
  Check: 768 + 32 + 352 = 1152 ✓
```

## Layout move — main field (the bill)

```
Title "BILL-2026-00003"           20px/600, line-height 28    margin-bottom 24px
Header field grid (3 col × 2 row) 240px col × 3 + 24px gutter × 2 = 720+48 = 768px ✓
  row 1: Vendor | Status (ring)  | Vendor's reference
  row 2: Bill date | Due date    | Open amount
  each field: label 12px/450 (16 lh) + 4px gap + value 14px/450 (20 lh) = 40px/row
  2 rows × 40 + 24px row-gap = 104px                          margin-bottom 32px

Line-items table, width 768px, columns 240 / 288 / 120 / 120 = 768 ✓
  ACCOUNT(240, left) · DESCRIPTION(288, left) · NET(120, right, tabular) · TAX(120, right, tabular)
  Header row              48px   accent-tint bg, 1px hairline bottom, 12px/600 caps labels, 0.04em tracking
  Data row (× real count) 40px   14px/450, tabular-nums on ACCOUNT code + NET/TAX, 1px hairline bottom
  Totals row               40px   1px hairline top, "Gross total" 14px/450 secondary + value 14px/600 tabular-nums accent-ink
  Table height (1 real line item): 48 + 40 + 40 = 128px       margin-bottom 32px

Actions row, height 40px
  [Record payment] primary button — accent-emphasis bg, white label 14px/600, 16px h-pad, 6px radius, 40px tall
  24px gap
  Void bill — text link, accent-ink, underline on hover, 14px/450

Main field content height: 28+24 + 104+32 + 128+32 + 40 = 388px of 772px available — remainder held as whitespace, matching the existing shot's own generous lower margin.
```

## Layout move — right rail (lifecycle axis)

```
Running-head "Document flow"      13px italic/400 (margin-serif role)   margin-bottom 24px
Vertical axis: 1px hairline, x=8px (local to rail), full node-block height

3 nodes, each block:
  ring marker  16px diameter, centered on axis line
  text block starts x=32px (axis + 24px gap):
    doc type   12px/450 secondary, sentence case ("Purchase order")
    doc code   14px/450 tabular-nums, primary text ("PO-2026-00114")
    date       12px/450 secondary
  node block height ≈ 72px, 32px gap between node centers

Node 1 — PO-2026-00114 — Purchase order — thin solid ring (posted/confirmed)
         "Sent Jun 8, 2026 · expected Jun 18"
Node 2 — GR-2026-00098 — Goods receipt — thin solid ring (confirmed)
         "Received Jun 20, 2026"
         ↳ margin note, attached below node 2, max-width 280px:
           13px italic/400 (margin-serif role), accent-ink color:
           "Received 2 days after the PO's expected date (Jun 18)."
Node 3 — BILL-2026-00003 — Vendor bill — CURRENT — thin solid ring + 6px filled
         accent-emphasis center dot ("you are here" / hand-checked fix)
         "Posted Jun 20, 2026"

Rail content height: 40 (head) + 3×72 (nodes) + 2×32 (gaps) + 36 (margin note extra) ≈ 356px of 772px available.
```

## Ring marker vocabulary (shared: header Status field + rail axis nodes)

| State | Render | Stroke color (OKLCH) |
|---|---|---|
| Confirmed/posted | thin solid, 1.5px | `oklch(0.5 0.12 150)` — reused from CURRENT.md's already-verified green, not a new sample |
| Pending/estimate | dashed, 1.5px, 3px dash/2px gap | `oklch(0.55 0.08 240)` blue-gray |
| Error/overdue | heavy solid, 3px | `oklch(0.5 0.18 25)` — reused from CURRENT.md's already-verified red |
| Draft | hollow, 1.5px, no fill | `oklch(0.75 0.01 58)` neutral gray |
| Closed | filled, no stroke | `oklch(0.30 0.01 58)` dark fill |

Header Status field for BILL-2026-00003 renders the confirmed/posted ring (16px) inline, left of the "Posted" value text (14px/450). This is the same grammar as the current-node marker in the rail — the two "the bill is posted" signals agree rather than contradicting each other on one screen.

## Type table

| Role | Face | Size/weight | Line-height | Notes |
|---|---|---|---|---|
| Title | Inter Variable | 20px/600 | 28px | Screen title only |
| Margin serif | Source Serif 4 Variable, italic | 13px/400 | 18px | Rail running-head + margin note ONLY — never on data |
| Body/data | Inter Variable | 14px/450 | 20px | Field values, table cells, button label weight bumped to 600 for CTA |
| Meta | Inter Variable | 12px/450 | 16px | Field labels, table header labels (600 wt, caps, 0.04em tracking on header row only), dates |

Tabular-nums declared on: NET, TAX, Gross total, all doc codes (PO-/GR-/BILL- + digits), Open amount, Bill/Due dates.

## Paired colors — computed ratios

Computed via Oklab→linear-sRGB (Björn Ottosson matrices) + WCAG relative-luminance, this session, **not** measured off a rendered pixel — marked **computed, not rendered**.

| Pair | OKLCH | Ratio | Target | Result |
|---|---|---|---|---|
| Primary text / substrate | `0.22 0.008 58` / `0.99 0.002 58` | **16.84:1** | body text | clears |
| Secondary text / substrate | `0.46 0.01 58` / `0.99 0.002 58` | **6.94:1** | meta text | clears |
| Accent-ink / substrate | `0.40 0.07 58` / `0.99 0.002 58` | **9.14:1** | dispatch flagged ≥7:1 | clears |
| White / accent-emphasis | `1 0 0` / `0.58 0.10 58` | **4.41:1** | dispatch flagged ≥4.5:1 | **misses by 0.09** — see unsatisfied below |
| Accent-ink text / accent-tint | `0.40 0.07 58` / `0.95 0.02 58` | **8.10:1** | — | clears |
| Text / substrate (dark) | `0.93 0.005 58` / `0.16 0.004 58` | **15.78:1** | — | clears |
| Accent-dark / substrate (dark) | `0.70 0.08 58` / `0.16 0.004 58` | **7.12:1** | dispatch flagged ≥4.5:1 | clears |
| Confirmed ring / substrate | `0.5 0.12 150` / `0.99 0.002 58` | **5.51:1** | ≥3:1 (UI, non-text) | clears |
| Pending ring / substrate | `0.55 0.08 240` / `0.99 0.002 58` | **4.65:1** | ≥3:1 (UI, non-text) | clears |
| Error ring / substrate | `0.5 0.18 25` / `0.99 0.002 58` | **6.40:1** | ≥3:1 (UI, non-text) | clears |

All pairs checked for linear-RGB gamut sign (no negative components) — none clipped.

## Content direction, one line

Every value on the screen (BILL-2026-00003, Acme Supplies Co, INV-260615, Jun 20/Jul 20 2026, USD 54.00, 2100 — GR/IR Clearing) is carried over verbatim from the existing `detail-vendor-bill.png` shot — the only invented content is the PO/GR predecessor codes and their dates, sized and dated to stay chronologically consistent with the bill's own real date, never presented as more line items or richer data than the source actually has.

## Modal note (referenced, not primary render)

"Void bill" opens a confirm-action modal (owned by sibling error/confirm states, not re-rendered here). Per dispatch: initial focus lands on **Cancel**, not the destructive Void action, set programmatically on open — stated here as the build requirement this surface's action row triggers.

## Focus state

`:focus-visible` only, 2px solid accent-ink (`oklch(0.40 0.07 58)`), 2px offset — applies to the primary button, the Void bill link, and both header/rail interactive elements (row expand, if the table grows past one line item).

## Embarrassment-gate self-check

- Read every OKLCH value in this file back against the dispatch's palette block — all match verbatim except the two ring hues (green/red), which are explicitly logged as reused from CURRENT.md rather than newly sampled, per the direction doc's own pattern for concept B.
- Split math verified twice: 768+32+352=1152 (inner content), +64(pad)+224(nav)... 1152+256(=224 nav+32 pad)=1408, 1440-1408=32 (right pad) ✓. Table columns 240+288+120+120=768 ✓.
- Terminology lock checked: "vendor," "warehouse"-adjacent GR/IR account label, no "supplier," no "product," no "SKU" anywhere on this surface.
- Ring vocabulary on the header Status field and the rail's current-node marker agree (both read confirmed/posted) rather than sending two different signals for one bill.
- The one number that did **not** clear its target is flagged below rather than silently rounded up — this is the finding the self-check exists to catch.
- Would a designer put their name on this: yes, with the accent-emphasis contrast flagged for the palette owner, not buried.

## Return

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/chart-table/04-vendor-bill-detail.md`
- **Composition anchor:** `right-rail-caption`
- **Background mode:** `flat-surface`
- **One line:** Wide bill field + narrow lifecycle-inspector rail, the margin note carrying the collision's "hand-checked correction" beside a chain that otherwise reads as machine-plotted fixes.
- **Unsatisfied:** white-on-accent-emphasis computes to **4.41:1**, not the dispatch's expected ≥4.5:1 — a 0.09 miss, likely inside rounding tolerance of the direction doc's own hand-computed A-concept figures but not one I can round away here. Flagging for Loop 1/palette owner rather than silently nudging `oklch(0.58 0.10 58)` myself (not mine to edit). Everything else in the dispatch — split ratio, line-item row heights, header 48px, four real seed values, terminology lock, modal-focus rule — is satisfied as specified.
