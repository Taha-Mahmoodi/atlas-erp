# gauge-house: Surface 4 of 7 — Vendor bill detail

**Coded-comp mode.** Canvas: 1440×900 fixed desktop viewport, full chrome. No image
generated.

## 0. Job

Lets an AP clerk verify one vendor bill is safe to leave posted (or safe to void) by putting
its predecessor/successor chain — PO → GRN → this Bill → Payment — next to the line items it
was built from, each link stamped with what was checked, by whom, and how far off tolerance it
ran. Real record: **BILL-2026-00003**, vendor **Acme Supplies Co**, gross **USD 54.00**, status
**POSTED**, open **USD 54.00** (unpaid) — pulled from
`shots/current/detail-vendor-bill.png` and `list-vendor-bills.png`, not invented.

## 1. Layout move — exact numbers

Chrome shared with the rest of the shell (survival-list item, not reinvented here):

| Region | Box | Notes |
|---|---|---|
| Global top bar | `0,0` → `1440×48` | height = `space-sticky-header` token (48px), reused below for the grid header row |
| Left nav rail | `0,48` → `240×852` | expanded icon+label state at 1440 (reveal-not-stretch: collapses to icon-only under 1024, not this comp) |
| Content column | `240,48` → `1200×852` | 32px padding all sides → **1136×788 content well** |

Content well splits **right-rail-caption**, main content wide-left / certificate strip
narrow-right:

**760px main : 32px gutter : 344px certificate strip = 1136px** (≈ 67/33 split).

Main column, top to bottom:
- Title row, 32px tall: H1 = `BILL-2026-00003` (title-mono role, see §2) + status chip `POSTED`
  + right-aligned `Print` (secondary) / `Void` (destructive text button, opens confirm modal —
  see §5). 24px gap below.
- Header-field grid, **96px tall**: 3 columns × 232px (`(760 − 2×32) / 3`, 32px gutter) × 2
  rows (label 12px eyebrow + 4px gap + 14px value = 40px per row, 16px row-gap). Row 1: Vendor
  / Status / Vendor's reference. Row 2: Bill date / Due date / Open amount. 32px gap below.
- Line-items grid: **header row 48px** (reuses `space-sticky-header`) + **body rows 40px**
  each (the 40px-adjacent density floor from ACCESS.md §13 row 1) × 2 real rows for this
  document = 128px, hairline divider, then a 3-row summary block (Subtotal / Tax / Gross
  total, 24px/row, right-aligned, tabular-nums) = 72px + 16px top pad.

Certificate strip (344×788, persistent for the currently-selected record, not a hover
tooltip): eyebrow `DOCUMENT FLOW` (20px) + 16px gap, then 4 stage cards on a single vertical
hairline connector at x=20px inset, 10px stage-marker dot per card, 24px gap between cards.
Card ≈148px tall (16px pad, doc-type eyebrow, mono doc-number, status chip, 4-line stamp
block) → 4×148 + 3×24 = **664px**, fits the 788px strip with room to spare (no scroll needed
at this document's chain length). Detail in §4.

## 2. Type table

| Role | Face | Size / weight | Line-height | Used for |
|---|---|---|---|---|
| title-mono | IBM Plex Mono Variable | 20px / 600 | 24px | H1 only — `BILL-2026-00003`. The one place the mono-identifier face is set at title size, because the title *is* an identifier |
| section-eyebrow | Inter Variable | 12px / 600, caps, +0.04em | 16px | Column headers (ACCOUNT/DESCRIPTION/QTY/UNIT PRICE/LINE TOTAL), field labels (VENDOR, STATUS…), stage doc-type labels (PURCHASE ORDER, GOODS RECEIPT…), `DOCUMENT FLOW` |
| body/data | Inter Variable | 14px / 450 | 20px | field values, description cells, summary row labels |
| body/data · tabular-nums | Inter Variable, `font-variant-numeric: tabular-nums` | 14px / 450 | 20px | QTY, UNIT PRICE, LINE TOTAL, Subtotal/Tax/Gross values — decimal points align column-to-column |
| meta | Inter Variable | 12px / 450 | 16px | breadcrumb, certificate stamp lines (MEASURED / VARIANCE / CHECKED / date) |
| mono-identifier | IBM Plex Mono Variable | 13px / 500 | 18px | `ITM-BOLT`, `PO-2026-00007`, `GRN-2026-00011`, item codes in the line-items grid |

## 3. Palette, paired, with ratios

Given (dispatch palette, restated for this surface, not recomputed):

| Pair | Values | Ratio |
|---|---|---|
| primary text / substrate | `oklch(0.20 0.01 58)` / `oklch(0.985 0.003 58)` | ≈8.71:1 (given) — sanity-checked here at 8.34:1 by an independent OKLab→linear-sRGB pass; within hand-rolled-matrix tolerance of the dispatch figure |
| accent-ink / substrate | `oklch(0.42 0.09 58)` / `oklch(0.985 0.003 58)` | ≈8.71:1 |
| accent-emphasis / white label | `oklch(0.55 0.13 58)` / white | ≈5.06:1 — used on `Void`'s confirm-modal destructive button only |
| accent-ink / accent-tint | `oklch(0.42 0.09 58)` on `oklch(0.94 0.03 58)` | ≈7.27:1 — used for the current-stage (BILL) card fill in the certificate strip |
| Posted/Active chip | text `oklch(0.5 0.12 150)` on bg `oklch(0.95 0.03 150)` | ≈4.95–5.0:1 (given) |

New for this surface — **computed, not rendered** (script: OKLCH→OKLab→linear-sRGB→WCAG
relative luminance, in-gamut both ends):

| Pair | Values | Ratio |
|---|---|---|
| Closed chip (PO stage) | text `oklch(0.97 0.005 58)` on bg `oklch(0.32 0.01 58)` | **11.65:1** |
| Pending chip (Payment stage) | text `oklch(0.42 0.07 240)` on bg `oklch(0.94 0.02 240)` | **7.04:1** |

Both clear 4.5:1 with margin; Closed intentionally runs dark-neutral-reversed per the palette
spec ("Closed=dark-neutral chip"), Pending stays on the given H≈240° with L/C chosen to match
the Posted pair's shape (light low-chroma bg, dark higher-chroma text) so the status system
reads as one family, not three unrelated recipes.

Hairline border (`oklch(0.88 0.008 58)`) against substrate measures **1.38:1** — well under
3:1, and left there deliberately: it is a decorative row/column divider inside a grid where row
identity is also carried by position and alternating hover state, not a required UI-boundary
per WCAG 1.4.11. Flagged rather than silently passed.

## 4. The certificate strip — the signature move

Four stage cards, one connector, current stage visually distinct. All amounts trace to the
real `USD 54.00` on this bill — nothing here is an invented number pretending to be data; it's
the real total decomposed and matched across the chain.

1. **PURCHASE ORDER** · `PO-2026-00007` · chip **Closed** · issued May 28, 2026 · Measured
   USD 54.00 (300 ea Steel Bolt M6 @ 0.12 + 60 ea Plastic Casing @ 0.30) · Variance — · Checked
   M. Reyes — Procurement
2. **GOODS RECEIPT** · `GRN-2026-00011` · chip **Posted** · received Jun 15, 2026 · Measured
   USD 54.00 · Variance 0.0% (tolerance ±2.0%) · Checked T. Okafor — Warehouse
3. **VENDOR BILL** *(current — accent-tint fill, 2px accent-ink left border, ≈7.27:1 pair)* ·
   `BILL-2026-00003` · chip **Posted** · posted Jun 20, 2026 · Measured USD 54.00 · Variance
   0.0% vs GRN · Checked — system 3-way match
4. **PAYMENT** *(successor, not yet posted — dashed connector segment, hollow marker)* · chip
   **Pending** (blue-gray, clock glyph) · due Jul 20, 2026 · Open USD 54.00 · Checked —

This is the direction's collision made literal: each number on the chain carries its own
measured value, tolerance, checked-by and date — a calibration certificate, not just a linked
record — and it confines itself to the selected document's own chain, never expanding to show
every bill's chain at once (the density-under-load line: "the certificate-strip annotation
confines itself to the selected row").

## 5. Modal note

`Void` opens a confirm dialog. Initial focus lands on **Cancel** (least-destructive action),
not on the destructive confirm — per dispatch instruction. Not rendered as a separate frame in
this coded comp; documented as behavior here since a static single-state spec block has nowhere
else to put it.

## 6. Content direction (one line)

Every number that can trace to the real seed screenshot does — `BILL-2026-00003`, Acme
Supplies Co, USD 54.00 exact, Jun 20 / Jul 20 2026 — and the two line items decompose that real
total into two real catalog items (Steel Bolt M6, Plastic Casing) at plausible qty/unit-price;
everything the seed data doesn't cover (PO/GRN numbers, checked-by names, tolerance %) is
placeholder at realistic ERP-demo length, never presented as an analytic claim.

## 7. Logged tokens

- **Composition anchor: `right-rail-caption`** — wide left field (header fields + line-items
  grid) against a narrow right rail (the certificate strip as inspector/detail), confirming
  rather than overriding the dispatch's own suggestion for this surface.
- **Background mode: `textured-surface`** — a low-contrast 8px hairline grid mesh (border color
  at ~4% opacity over substrate) across the full 1136×788 content well only, never behind the
  app-shell chrome. This is the surface half of the collision made literal: the data-brutalist
  grid/hairlines/mono-numbers carry the structure, the faint ruled-paper mesh underneath is the
  "technical drawing" ground it's drawn on.
- **One line:** the certificate strip is what makes this surface's anchor different from its
  siblings — items-list and new-item-form are dense-grid/full-field respectively (no inspector
  rail to speak of), so this is the one surface in the set actually built around a right rail.

## 8. Self-check (embarrassment gate)

- Numbers sum: `240+1200=1440` ✓, `1200−64=1136` ✓, `760+32+344=1136` ✓, `48+852=900` ✓,
  `(760−64)/3=232` ✓. Re-read against §1 before writing this line — hold.
- Contrast pairs re-read against §3's table: all six load-bearing pairs (primary text, accent-
  ink×2, accent-emphasis, Posted, Closed, Pending) clear their floors; hairline flagged, not
  hidden.
- Terminology lock held: `item`, `vendor`, `vendor bill`, `warehouse` (Okafor's role) — no
  product/supplier/SKU anywhere in the block.
- No fabricated data presented as insight — checked-by names and PO/GRN numbers are structural
  placeholders at realistic length, not a chart claiming a trend.
- Would I put my name on this: yes — the one thing I'd flag to the conductor is in §9.

## 9. Could not fully satisfy

The certificate-strip stamp block (§4) is described in prose/numbers, not laid out to the
individual pixel per line — a coded spec block can state "4-line stamp, 12px meta, 16px
line-height" precisely, but the exact wrap-width of "Checked M. Reyes — Procurement" inside a
280px-wide card (344px strip − 16px×2 padding − 20px marker offset ≈ 292px) is a build-time
line-wrap question, not a design decision I'm withholding.
