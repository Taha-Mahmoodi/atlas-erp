# press-panel: Surface 4 of 7 — Vendor bill detail

Concept: **press-panel** — data-brutalist (dominant/structure) × claymorphism (bounded/surface,
gated on restraint). Flat instrument panel; the ONE dimensional object is what the hand reaches
for. Restraint rule: clay appears in exactly two roles system-wide — the primary CTA button and
the "pending" status pill — both of which land on this surface, since BILL-2026-00003 is pending
approval. No annotation layer, no marginalia, anywhere on this screen.

Canvas: **1440×900**, fixed viewport, full chrome, real row counts. Platform mode: N/A (desktop
tool-shaped web surface).

---

## Composition tokens

- **Composition anchor: `dense-grid`** — the line-items table is the largest single field on the
  canvas and the eye lands there first; the header metadata strip, the document-flow list, and
  the nav/top chrome are all subordinate to it in scale and in visual weight.
- **Background mode: `flat-surface`** — one solid substrate throughout (`oklch(0.98 0.002 58)`),
  every panel, table, and list sits inline on it with hairline borders as the only separator.
  No texture, no gradient, no image, anywhere on this surface.
- **One line:** the table owns the canvas and stays flat like everything else; the only thing
  that lifts off the page is the Approve button and the Pending pill, so the eye has exactly one
  place it can press.

---

## Layout move, with numbers

**Global chrome** (shared shell, restated here only to place the content region):
- Left nav rail: `0,0` → `240×900`, background substrate, `1px` hairline border on right edge.
  Nav rows `40px` tall, text-only labels (no icon glyphs — no platform mode is bound on this
  surface, so no icon system is asserted): Items, Vendors, Customers, Warehouses, Journal
  Entries, **Vendor Bills** (active — active row gets a flat `accent-tint` background fill, not
  clay: active-state is a flat state, not a pressable one).
- Top bar: `240,0` → `1440×56`, `1px` hairline border on bottom edge. Left-aligned: breadcrumb
  "Vendor Bills / BILL-2026-00003" (meta, secondary text) above title "BILL-2026-00003" (title,
  primary text). Right side empty — no search, no icon cluster; plainness holds here too.

**Content region:** `240,56` → `1440×900`, i.e. `1200×844`, `32px` padding on all sides →
content width **1136px**.

1. **Header metadata strip — 48px tall, 1136px wide.** Four fields laid side by side, each
   column **260px** wide with **32px** gutters between (`260×4 + 32×3 = 1136`). Each field is
   label-over-value: label in `meta` (12px/450, secondary text), value in `body` (14px/450,
   tabular where numeric) directly below with a `4px` gap — total field height `~30px`, centered
   in the `48px` band.
   - Vendor: "Meridian Supply Co."
   - Bill Date: "2026-07-28" (tabular)
   - Due Date: "2026-08-27" (tabular)
   - Status: **clay pill** — "Pending Approval" (this is the second of the two system-wide clay
     roles; see Colors below for its construction). Any other status on this record type
     (Approved, Paid, Void) would render as a flat chip — `accent-tint` fill, `accent-ink` text,
     no elevation — this is the only field on the surface with two possible renders.
   - `1px` hairline border below the strip, full 1136px width, `24px` margin above and below to
     the next block.

2. **Document-flow list — plain, bordered, factual.** Section label "Document flow" (meta,
   secondary text, `12px`), `8px` below it a bordered container, full `1136px` width, `1px`
   hairline border, `4px` corner radius.
   - Column header row: **32px** tall, meta (12px/450, secondary text): "Type · Reference ·
     Date," flat, no background fill.
   - Three data rows, **40px** each (`120px` total body height), `1px` hairline divider between
     rows, body type (14px/450):
     1. Purchase Order — `PO-2026-00041` — `2026-07-14`
     2. Goods Receipt — `GRN-2026-00038` — `2026-07-26`
     3. Vendor Bill — `BILL-2026-00003` — `2026-07-28` (current record: primary-text weight
        stays the same 450 as its siblings — the only distinction is a `1px` left border in
        `accent-ink` on this row, not a badge, not a label, not a plotted marker. That single
        border rule is the whole "you are here" — no annotation layer added to earn it.)
   - No arrows, no connecting lines, no plotted diagram — three rows in a list, read top to
     bottom, is the entire chain.
   - `32px` margin below the container to the next block.

3. **Line items table — the dense-grid anchor, real row count.** Full `1136px` width.
   - Header row: **40px**, meta (12px/450, secondary text), left-aligned except numeric columns
     which are right-aligned to match their data below.
   - Columns (sum to 1136px): Item `110px` · Description `420px` · Qty `90px` (right, tabular) ·
     Unit Price `170px` (right, tabular) · Tax `130px` (right, tabular) · Line Total `216px`
     (right, tabular).
   - Six line-item rows, **44px** each (`264px` total), `1px` hairline divider between rows, body
     (14px/450, tabular for every numeric cell, decimal-aligned):
     | Item | Description | Qty | Unit Price | Tax | Line Total |
     |---|---|---|---|---|---|
     | ITM-0231 | 4-post pallet rack, 96in | 6 | 214.00 | 17.12 | 1,301.12 |
     | ITM-0198 | Rack shelf, wire deck | 24 | 38.50 | 9.24 | 933.24 |
     | ITM-0304 | End-of-aisle guard | 8 | 61.00 | 4.88 | 492.88 |
     | ITM-0112 | Beam connector, pair | 48 | 6.75 | 3.24 | 327.24 |
     | ITM-0267 | Freight surcharge | 1 | 145.00 | 0.00 | 145.00 |
     | ITM-0059 | Installation labor | 12 | 65.00 | 0.00 | 780.00 |
   - Totals: three rows, **40px** each, right-aligned in the Line Total column, label in meta to
     its left: Subtotal `3,979.48` · Tax `34.48` · **Total `4,013.96`** (Total row uses the same
     body weight as everything else — no bolding invented to make it "pop"; the row's position at
     the foot of the table plus a `1px` top hairline rule is what marks it, consistent with the
     doc-flow row above).

4. **Action bar — bottom of content region, right-aligned.** Two buttons, both **44px** tall,
   `16px` gap between them.
   - **Reject** — flat, `1px` hairline border, `accent-ink` text, transparent fill, `12px`
     corner radius, `24px` horizontal padding, min-width auto. Opens a confirm modal on click;
     per spec, that modal's initial focus lands on **Cancel**, not on the destructive action —
     stated here as the surface's interaction contract even though the modal itself is not
     rendered on this comp (one surface, one state).
   - **Approve** — the ONE clay object on this screen alongside the pending pill. `132px`
     min-width, `24px` horizontal padding, `12px` corner radius, label in `clay-button` role
     (15px/600, white). This is the only pressable surface with elevation on the entire screen.

**Focus ring:** `2px` solid `accent-ink`, `2px` offset, on every focusable element including the
clay Approve button — a hard ring, never a shadow trick, even where the element it sits on
already has its own shadow.

---

## Type table

| Role | Face | Size | Weight | Line-height | Numerals |
|---|---|---|---|---|---|
| title | Inter Variable | 20px | 600 | 26px | — |
| body / data | Inter Variable | 14px | 450 | 20px | tabular where numeric |
| meta | Inter Variable | 12px | 450 | 16px | tabular where numeric |
| clay-button label | Inter Variable | 15px | 600 | 20px | — |

No fifth role invented for the pending pill or the table's totals row — both reuse `meta` and
`body` respectively, per the direction's restraint elsewhere.

---

## Colors, paired, with ratios

All ratios computed fresh via OKLCH → OKLab → linear sRGB → WCAG relative luminance, **computed,
not rendered** — read back against the palette below before returning this spec.

| Role | OKLCH | ~sRGB hex (computed) | Paired against | Ratio (computed) | Passes |
|---|---|---|---|---|---|
| substrate | `oklch(0.98 0.002 58)` | `#F9F8F7` | — | — | — |
| primary text | `oklch(0.19 0.006 58)` | `#161311` | substrate | **17.44:1** | AA/AAA body, large |
| secondary text | `oklch(0.44 0.008 58)` | `#56514E` | substrate | **7.34:1** | AA/AAA body |
| hairline border | `oklch(0.86 0.005 58)` | `#D4D0CE` | substrate | 1.45:1 | decorative divider only — not a text pair, not load-bearing for the 3:1 non-text UI floor since dividers carry no meaning on their own |
| accent-ink | `oklch(0.40 0.10 58)` | `#6E3700` | substrate | **8.97:1** | AA/AAA body |
| accent-ink | `oklch(0.40 0.10 58)` | `#6E3700` | accent-tint | **7.68:1** | AA/AAA body |
| accent-emphasis (clay) | `oklch(0.60 0.14 58)` | `#BC670C` | substrate (as a shape, not text) | — | n/a, non-text |
| white (clay-button label) | `#FFFFFF` | — | accent-emphasis | **4.12:1** | **fails AA (4.5:1) for 15px/600** — flagged below |
| primary text | `oklch(0.19 0.006 58)` | `#161311` | accent-tint | **14.94:1** | AA/AAA body |

---

## Content direction

One line: every field on this screen holds a plausible-length real value (vendor name, ISO
dates, six real-shaped line items, a document chain that actually chains) — nothing reads as
lorem, nothing invents a brand, and the only two objects that lift off the substrate are the
things a hand is actually meant to press.

---

## Embarrassment-gate self-check

- Hexes read back against the palette table above — all seven roles present and traced through
  the OKLCH pipeline, not eyeballed. **Pass.**
- Body-size type (14px, primary/secondary text) sits at 7.34:1–17.44:1 against substrate —
  comfortably legible. **Pass.**
- Collision readable: the table, the doc-flow list, the header strip, and the nav are all flat —
  same hairline, same 450-weight body type, no shadows, no radius beyond 4px anywhere except the
  two clay objects. The clay Approve button and the clay Pending pill are the only things with
  elevation on the canvas, and they're the only things a hand would reach for. **Pass.**
- No annotation layer, no marginalia — the doc-flow chain is a bordered list with one `1px`
  accent-ink rule marking "current," not a plotted diagram. **Pass.**
- Composition anchor (`dense-grid`) and background mode (`flat-surface`) both describe what's
  actually on the canvas, not an aspiration. **Pass.**
- No garbled text, no invented logo, no fabricated brand, no superlative copy anywhere on the
  surface. **Pass.**

**Not satisfied — flagged rather than silently shipped:** the clay-button label (white, 15px/600
on `accent-emphasis` `#BC670C`) computes to **4.12:1**, short of the 4.5:1 AA floor for
normal-size text (15px/600 doesn't clear the "large text" bold threshold of ~18.66px). This is a
property of the palette values as specified in the dispatch, not a rendering choice made here —
flagging it rather than unilaterally darkening the clay swatch, since accent-emphasis is a
system-wide token and this surface doesn't own it. A ~0.04–0.06 drop in L on accent-emphasis (to
roughly `oklch(0.54–0.56 0.14 58)`) would clear 4.5:1 without changing its hue or its role.
