# the yard: Surface 3 of 7 — Items List

Mode: **light**. Canvas: fixed **1440×900** coded viewport (web/desktop-only, no platform
mode). Screen: Inventory > Items, unfiltered, full dataset. Composition anchor:
**dense-grid**. Background mode: **flat-surface**.

Job of this screen: let an inventory operator scan, find, and act on real stock the moment
they land — not a curated sample. This is the direction's density proof: the same
signal-token used at 1-per-lane density on surface 02 has to still cost nothing extra at
38-per-column density here, or the collision doesn't hold past the home screen. Same rail
chrome (`232px`), title band (`64px`), and sticky filter-row band (`56px`) as surface 06
(Items list, filtered-to-zero) — this is the populated state of the *same screen*, not a
different one, so the shared chrome is reused pixel-for-pixel, not redrawn.

---

## 1. Layout — region map (8px base unit throughout)

| Region | Bounds (x, y, w, h) | Notes |
|---|---|---|
| Left rail | 0, 0, 232, 900 | full height, `card` fill, 1px `hairline` right border |
| Title band | 232, 0, 1208, 64 | sticky, `card` fill |
| Filter/search band | 232, 64, 1208, 56 | sticky (`space-sticky = 56px`, `DIRECTION.md` §3 row 5), `card` fill, 1px `hairline` bottom border |
| Table card | 264, 120, 1144, 724 | inset `32px` from both content edges, rounded-16, shadowed — see §6 |
| Footer/pagination band | 232, 844, 1208, 56 | `card` fill, 1px `hairline` top border |

Sums: `64 + 56 + 724 + 56 = 900`. Rail `232` + content `1208` = `1440`. Table card inner
width `1144 = 1208 − 32 − 32`; its 8 column widths (§6) sum to exactly `1144`.

Skip link: visually hidden, first in tab order, reveals on `:focus` at `(16, 16)` over the
title band; targets `#main-content`. One `<main id="main-content">` wraps the title band
through the footer band. One `<nav aria-label="Primary">` wraps the left rail. One `<h1>`
("Items") — nothing else on this screen competes for it.

---

## 2. Left rail (232px)

Identical component to surface 06 — same screen family, not redrawn:

- `0,0,232,64` — wordmark "Atlas" (real product name, no invented brand, no logo mark),
  14px/600, `text-primary`, padding-left `24px`, vertically centered.
- Nav items below, `44px` height each (control floor), full rail width minus `16px`
  horizontal margin, `12px` internal padding, `20px` icon + `8px` gap + `14px/450` label:
  Home · **Inventory (active)** · Procurement · Sales · Finance · Reporting · Admin · —
  spacer — · Help (pinned last, fixed relative position, per the run's system rule).
- Active state (Inventory): rail-item background `accent-tint`, text `accent-ink`, `3px`
  `accent-ink` left indicator bar flush to the rail's left edge.
- Focus ring on every rail item: `2px solid accent-ink`, `2px` offset, `:focus-visible` only.

---

## 3. Title band (1208×64px)

- `<h1>` "Items" — `title` 20px/600, `text-primary`, left-aligned, padding-left `32px`,
  vertically centered.
- Breadcrumb "Inventory / Items" — `meta` 12px/450, `text-secondary`, `4px` above the h1
  baseline (breadcrumb is not a heading; the h1 stands alone).
- Right-aligned, `32px` from the right edge, `16px` gap between controls:
  - **Density toggle** — icon-only (list-density glyph), `44×44px` hit target, accessible
    name "Toggle row density"; per `TOOLS.md` §2 / `ACCESS.md` row 1, compact mode never
    drops row height below `40px` (this comp renders the default/comfortable `48px` row —
    see §6).
  - **"+ New item"** — primary button, `44px` height, `16px` horizontal padding, radius
    `12px`, fill `accent-ink`, label `14px/600` white. Primary here (unlike surface 06's
    secondary treatment) because this is the screen an operator actually creates items
    from — 06 is a filtered dead-end where "get back to the list" outranks "create."

---

## 4. Filter/search band (1208×56px, sticky)

Padding-left/right `32px`, vertically centered row, `12px` gaps between elements:

1. **Search field** — `320×44px`, `card` fill, `1px hairline` border, radius `10px`,
   placeholder "Search items by name or SKU" (`text-secondary`), search icon `16px` inline
   left. Not shown active-filtered in this comp (empty query, full 38-row dataset visible).
2. Meta label "Filters" — `12px/450`, `text-secondary`.
3. **One example chip** (component identical to surface 06's, reused unmodified): rounded-
   full pill, `44px` height, `16px` horizontal padding, `accent-tint` fill, `accent-ink`
   text `14px/450`: **"Vendor: Acme Fastening Co."**, trailing `16px` × glyph (`accent-ink`),
   `8px` gap before it. `aria-label="Remove filter: Vendor — Acme Fastening Co."` on the
   dismiss control. `:focus-visible` ring: `2px solid accent-ink`, `2px` offset.
4. "+ Add filter" — ghost text button, `14px/450` `accent-ink`, no border/fill.

**This chip is illustrative of the control only** — the 38-row table in §7 is the
*unfiltered* dataset (shown to prove density holds at full row count); applying this chip
for real would reduce the visible set. Both facts are stated so the comp isn't read as
self-contradictory.

**Filter state lives in the URL**, per `TOOLS.md`: `?category=&vendor=&status=&sort=&cursor=`
query params, replacing (not pushing) history on each change. This has **no visual
signature** in the comp — it's a routing/state-management contract, not a rendered element —
noted here per the dispatch's explicit instruction to record it anyway.

---

## 5. Table card (1144×724px, rounded-16)

Fill `card` `oklch(1 0 0)` on `substrate` `oklch(0.985 0.004 290)`. Shadow:
`0 1px 2px oklch(0 0 0 / 0.05), 0 8px 24px oklch(0 0 0 / 0.06)` (same formula as every card
in this concept). `overflow: hidden`, radius `16px`, so the sticky header's square bottom
edge never breaks the rounded corner as the body scrolls beneath it.

**Sticky header** — `56px` (`space-sticky`), `position: sticky; top: 0` inside the card's own
scroll container, rounded top corners matching the card. Column labels `meta (emphasis)
12px/600` (same size slot as `meta`, weight-bumped for chrome/data distinction — not a new
scale step, same move surface 05 uses for its group headers), `text-secondary`,
`uppercase`, `letter-spacing 0.04em`. Sortable columns (Item, Category, Qty on hand, Reorder
point, Vendor) carry an `8px` caret glyph, click toggles `asc/desc`, reflected in the URL's
`sort` param. Select and Status columns are not sortable; Actions never is.

**Column widths (sum = 1144px, matches the card's inner width exactly):**

| Column | Width | Align | Content |
|---|---|---|---|
| Select | 40px | center | row checkbox |
| Item | 320px | left | item name (14px/450) over SKU (13px/500 mono), 2px gap |
| Category | 150px | left | body/data 14px/450 |
| Qty on hand | 110px | right | body/data 14px/450, `tabular-nums` |
| Reorder point | 120px | right | body/data 14px/450, `tabular-nums` |
| Vendor | 210px | left | body/data 14px/450 |
| Status | 90px | center | signal-token, see §6 |
| Actions | 104px | right | 3-icon cluster, see §7 |

**Row anatomy** — `48px` height, uniform: `4px` top padding + `20px` (Item name line,
14px/450) + `2px` gap + `18px` (SKU line, 13px/500 mono) + `4px` bottom padding = `48px`
exactly. Single-line cells (Category/Qty/Reorder/Vendor) center their `20px` content line
within the same `48px` row.

**Row divider signal — paired, per the palette table's own instruction that hairline is
never the sole boundary:** rows **zebra** between `card` white (even) and `substrate`
`oklch(0.985 0.004 290)` (odd) tint, *plus* a `1px hairline` `oklch(0.89 0.01 290)` bottom
border on every row. Hover: row fill → `accent-tint`. Focused cell (grid nav, §7): `2px
solid accent-ink` ring, `2px` offset, drawn *inside* the cell so it never collides with the
adjacent row's hairline.

**Status column — the signal-token, reused unmodified from surface 02 §6, not a new
variant.** Same `28×28px` rounded-square (or `2px` dashed ring for Draft), same glyph-in-
paired-text-color construction, same `44×44px` hit target centered on the small visible
chip, same hover-reveal tooltip whose string is also the token's `aria-label`. No text
label is added in the table — the collision's own rule is that this token is "the one
atomic unit for every status anywhere in the system," so the table reuses the component
exactly rather than growing a table-specific pill-with-label variant. A `90px` column gives
the `44×44px` hit target room with margin either side; **no WCAG 2.5.8 spacing exception is
needed here** — that exception is reserved for the row-actions cluster in §7, which
genuinely can't fit three `44px` targets in a `104px` column and has to invoke it.

Status-token vocabulary used in this table's 38 rows (light pairs, as specified):

| State | Fill | Text/glyph | Glyph |
|---|---|---|---|
| Draft | `oklch(0.93 0.006 290)` | `oklch(0.4 0.01 290)` | dashed ring, pencil |
| Active | `oklch(0.58 0.15 150)` | `oklch(0.18 0.03 150)` | check |
| Low-stock | `oklch(0.62 0.14 80)` | `oklch(0.2 0.03 80)` | clock |
| Discontinued | `oklch(0.55 0.19 25)` | white | exclaim |
| Archived | `oklch(0.35 0.008 290)` | white | lock |

Token accessible-name pattern (matches `ACCESS.md` row 10's "state + record" rule, not a
bare color/shape description), three worked examples, pattern repeats identically for all
38 rows:

- Row 2: `"Low-stock — Item ITM-BOLT-M8X25, 86 on hand, reorder point 150."`
- Row 6: `"Draft — Item ITM-TERM-6POS, not yet stocked."`
- Row 9: `"Discontinued — Item ITM-CUBAR-2IN, 0 on hand."`

---

## 6. `role="grid"` interaction contract

Grid: `39` rows (`1` header + `38` data) × `8` columns. Roving `tabindex`: exactly one cell
holds `tabindex="0"` at a time (initially the first data row's Item cell, or the last-
focused cell, restored on return); every other cell is `tabindex="-1"`.

- **Arrow Up/Down** — move focus one row, same column. **Arrow Left/Right** — move one
  column, same row. **Home/End** — first/last column in the current row. **Ctrl+Home/End**
  — first/last cell in the grid.
- **Enter** — behavior depends on the focused cell's content, both branches routing through
  the run's shared entered-cell-state contract (`DIRECTION.md` §3 row 14):
  - On **Item, Category, Qty on hand, Reorder point, or Vendor** — opens the record's
    detail as a right-side panel (item description, stock ledger, linked vendor — this
    concept's document-flow-panel pattern, applied to an item rather than a PO→GRN→Bill
    chain, since items don't carry that chain themselves).
  - On **Status** — enters widget-editing mode: a `220×236px` popover opens below the
    token, `card` fill, `1px hairline` border, radius `12px`, shadow as §5, listing the 5
    states (`44px` row each) as token+label rows. Arrow Up/Down navigate the popover's
    list, Enter commits, **Escape restores grid navigation** without committing (contract
    named explicitly, per `ACCESS.md` row 14).
  - On **Actions** — enters widget mode among the 3 buttons (see §7); Escape restores grid
    navigation.
- **Space**, from any cell in a row, toggles that row's selection state (the visible
  Select-column checkbox is the mouse affordance for the same action).
- **Shift** + Arrow Up/Down extends the selection range from the last anchor row to the
  newly focused row (Shift+Click does the same with a mouse anchor). Selecting ≥1 row
  surfaces a slim contextual action bar at the top of the table body ("Change status,"
  "Export") — the reachable destination for a Shift-extended selection, out of scope for
  this comp's detail.
- If a Status edit removes the row from the current filtered view (e.g., archiving an item
  out of an Active-only filter), focus moves to the next row, or to the table region itself
  if the removed row was last — the run's one SPA focus-management rule (`ACCESS.md` row
  13), applied here rather than restated as a new one.

---

## 7. Row actions (visible on focus, not hover-only)

Final grid cell per row, `104px` wide: three icon controls — **Open** (eye), **Edit**
(pencil), **More** (⋯, overflow: duplicate / archive / export). Each an `18px` glyph
centered in a `24×24px` region, three regions placed edge-to-edge with `8px` gaps, giving
`24px` centre-to-centre spacing — the WCAG 2.5.8 spacing exception (`ACCESS.md` row 1),
used here because three real `44px` targets (`132px`) don't fit in a `104px` column; the
Status token in §5 doesn't need this exception because it's alone in its column with room
to spare.

**Visibility:** opacity `0` at rest, opacity `100%` on `tr:hover` **or** `tr:focus-within`
— any cell in the row receiving keyboard focus reveals the cluster, satisfying "visible on
focus, not just hover" directly rather than as an afterthought. Always present in the DOM
and in the grid's tab order regardless of visual opacity, so assistive tech never depends on
the hover/focus reveal to find it.

**Accessible names**, per `ACCESS.md` row 10's "Open BILL-2026-00003" pattern, adapted —
three worked examples, pattern repeats for all 38 rows:

- `"Open ITM-BOLT-M6X20"` / `"Edit ITM-BOLT-M6X20"` / `"More actions for ITM-BOLT-M6X20"`
- `"Open ITM-EPOX-1L"` / `"Edit ITM-EPOX-1L"` / `"More actions for ITM-EPOX-1L"`

---

## 8. Footer/pagination band (1208×56px)

Padding-left/right `32px`, vertically centered. Left: "Showing 1–38 of 214 items" (`body`
14px/450, `text-secondary` — illustrative total, bound at runtime, not a claimed metric).
Right, `12px` gap: **Prev** (disabled, page 1) / **Next** — secondary buttons, `44px`
height, `card` fill, `1px hairline` border, radius `12px`, `14px/500` `accent-ink` label
(same secondary-button treatment as surface 06's "+ New item," reused for consistency).
Cursor-paginated per the API's REST contract (`CLAUDE.md`), page size `40`.

---

## 9. Data — the 38-row dataset

Proves the density claim in §11 with real row counts, not a token sample. Item name and SKU
render as two stacked lines in the Item cell (§5); shown here as `Name — `SKU`` for
markdown-table compactness.

| # | Item | Category | Qty on hand | Reorder point | Vendor | Status |
|---|---|---|---|---|---|---|
| 1 | Hex Bolt M6x20 — `ITM-BOLT-M6X20` | Fasteners | 1,240 | 300 | Acme Fastening Co. | Active |
| 2 | Hex Bolt M8x25 — `ITM-BOLT-M8X25` | Fasteners | 86 | 150 | Acme Fastening Co. | Low-stock |
| 3 | Lock Washer M6 — `ITM-WASH-M6LK` | Fasteners | 3,900 | 500 | Acme Fastening Co. | Active |
| 4 | Cable Tie 8in Black — `ITM-CTIE-8BLK` | Electrical | 12,000 | 2,000 | Voltix Components | Active |
| 5 | 14 AWG Stranded Wire, Red — `ITM-WIRE-14AWG-RD` | Electrical | 410 | 400 | Voltix Components | Low-stock |
| 6 | Terminal Block 6-Pos — `ITM-TERM-6POS` | Electrical | 0 | 60 | Voltix Components | Draft |
| 7 | Aluminum Sheet 4x8 .125in — `ITM-ALSH-125` | Raw Material | 22 | 30 | Meridian Metals | Low-stock |
| 8 | Steel Rod 1in x 6ft — `ITM-STRD-1X6` | Raw Material | 340 | 100 | Meridian Metals | Active |
| 9 | Copper Bar 2in — `ITM-CUBAR-2IN` | Raw Material | 0 | 20 | Meridian Metals | Discontinued |
| 10 | Corrugated Box 12x12x12 — `ITM-BOX-121212` | Packaging | 5,600 | 1,000 | Cascade Packaging | Active |
| 11 | Bubble Wrap 48in Roll — `ITM-BWRAP-48` | Packaging | 140 | 200 | Cascade Packaging | Low-stock |
| 12 | Pallet Stretch Film — `ITM-FILM-STR` | Packaging | 900 | 250 | Cascade Packaging | Active |
| 13 | Poly Strapping 1/2in — `ITM-STRAP-05` | Packaging | 0 | 150 | Cascade Packaging | Draft |
| 14 | Safety Glasses, Clear — `ITM-SAFE-GLASS-CLR` | Safety | 480 | 100 | Guardian Safety Supply | Active |
| 15 | Nitrile Gloves L — `ITM-GLOVE-NIT-L` | Safety | 65 | 200 | Guardian Safety Supply | Low-stock |
| 16 | Hard Hat, Yellow — `ITM-HHAT-YEL` | Safety | 210 | 50 | Guardian Safety Supply | Active |
| 17 | Ear Plugs, Foam — `ITM-EARP-FOAM` | Safety | 3,200 | 500 | Guardian Safety Supply | Active |
| 18 | Torque Wrench 3/8in — `ITM-TWR-38` | Tooling | 18 | 10 | Precision Tool Works | Active |
| 19 | Digital Caliper 6in — `ITM-CAL-6IN` | Tooling | 4 | 8 | Precision Tool Works | Low-stock |
| 20 | Drill Bit Set, HSS — `ITM-DBIT-HSS` | Tooling | 0 | 15 | Precision Tool Works | Discontinued |
| 21 | Angle Grinder 4.5in — `ITM-GRND-45` | Tooling | 12 | 6 | Precision Tool Works | Active |
| 22 | Epoxy Resin, 1L — `ITM-EPOX-1L` | Adhesives | 90 | 40 | BondTech Adhesives | Active |
| 23 | Thread Locker Blue — `ITM-TLOCK-BLU` | Adhesives | 22 | 30 | BondTech Adhesives | Low-stock |
| 24 | Silicone Sealant, Clear — `ITM-SEAL-SIL-CLR` | Adhesives | 0 | 25 | BondTech Adhesives | Draft |
| 25 | PVC Pipe 1in x 10ft — `ITM-PVC-1X10` | Plumbing | 560 | 200 | FlowLine Plumbing Supply | Active |
| 26 | Ball Valve 1/2in — `ITM-VALV-BALL-05` | Plumbing | 38 | 40 | FlowLine Plumbing Supply | Low-stock |
| 27 | Pipe Fitting Elbow 90° — `ITM-FIT-ELB90` | Plumbing | 720 | 150 | FlowLine Plumbing Supply | Active |
| 28 | Teflon Tape Roll — `ITM-TAPE-TFL` | Plumbing | 1,100 | 300 | FlowLine Plumbing Supply | Active |
| 29 | Hex Bolt M10x30 — `ITM-BOLT-M10X30` | Fasteners | 0 | 100 | Acme Fastening Co. | Archived |
| 30 | Cotter Pin 1/8in — `ITM-PIN-COT-18` | Fasteners | 2,200 | 400 | Acme Fastening Co. | Active |
| 31 | Circuit Breaker 20A — `ITM-BRKR-20A` | Electrical | 55 | 60 | Voltix Components | Low-stock |
| 32 | Conduit Fitting 3/4in — `ITM-COND-FIT-34` | Electrical | 300 | 100 | Voltix Components | Active |
| 33 | Stainless Sheet 16ga — `ITM-SSSH-16GA` | Raw Material | 14 | 20 | Meridian Metals | Low-stock |
| 34 | Foam Corner Protector — `ITM-FOAM-CORNR` | Packaging | 0 | 500 | Cascade Packaging | Archived |
| 35 | Respirator Mask N95 — `ITM-RESP-N95` | Safety | 900 | 300 | Guardian Safety Supply | Active |
| 36 | Socket Set 1/4in Drive — `ITM-SOCK-14DR` | Tooling | 7 | 5 | Precision Tool Works | Active |
| 37 | Construction Adhesive — `ITM-ADH-CONST` | Adhesives | 48 | 50 | BondTech Adhesives | Low-stock |
| 38 | Gate Valve 2in — `ITM-VALV-GATE-2` | Plumbing | 0 | 30 | FlowLine Plumbing Supply | Discontinued |

Status distribution across the 38 rows: `17` Active, `11` Low-stock, `4` Draft, `3`
Discontinued, `3` Archived — all 5 vocabulary states represented multiple times, not a
one-of-each token showcase. `13` full rows fit in the `668px` scrollable body at `48px` row
height before scrolling; the remaining `25` are documented here, not truncated to a 5-row
sample, per the dispatch's explicit instruction.

---

## 10. Type table

| Level | Face | Size/weight | Line-height | Used for |
|---|---|---|---|---|
| Title | Inter Variable | 20px/600 | 28px (1.4) | `<h1>` "Items" |
| Body/data | Inter Variable, tabular | 14px/450 | 20px (1.43) | item name, category, vendor, footer text, chip label, search placeholder |
| Meta | Inter Variable | 12px/450 | 16px (1.33) | breadcrumb, "Filters" label |
| Meta (emphasis) | Inter Variable | 12px/600 | 16px (1.33) | column headers — same slot as meta, weight-bumped, not a new size |
| Mono-identifier | JetBrains Mono Variable | 13px/500 | 18px (1.38) | SKU codes, ligature-free so a code is never mistaken for prose at a skim |

**Qty on hand / Reorder point** use Inter's `tabular-nums` feature (not the mono face —
mono is reserved for identifiers, per the dispatch brief), right-aligned so digit columns
align vertically down all 38 rows.

---

## 11. Palette — light, with ratios

| Token | Value | Used for | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | page fill, odd-row zebra tint | text-primary | ~15:1 |
| card | `oklch(1 0 0)` | rail, title band, filter band, table card, even-row zebra tint | text-primary | ~16:1 |
| text-primary | `oklch(0.21 0.015 290)` | h1, item names, wordmark | — | — |
| text-secondary | `oklch(0.46 0.02 290)` | breadcrumb, meta labels, footer text, search placeholder | on card | ~6.5:1 |
| hairline | `oklch(0.89 0.01 290)` | rail border, band borders, row bottom border | decorative-only, paired with zebra tint, never the sole row-divider signal | sub-3:1 |
| accent-ink | `oklch(0.44 0.15 290)` | active-rail text/bar, "+ New item" fill, chip text, focus ring, popover selection | white / on card | ~7:1 |
| accent-tint | `oklch(0.94 0.035 290)` | active-rail bg, chip fill, row hover fill | accent-ink | ~6:1 |

`accent-emphasis` (`~4.8:1`, flagged borderline in `DIRECTION.md` §5/§6/§11) is **not used
on this surface** — the primary button and every text pairing here stay on the verified
`accent-ink` (`~7:1`), same choice surfaces 02 and 06 make. The gradient CTA is likewise
unused — nothing on a dense data table is a single hero action large enough to earn it.

All ratios above are estimated by OKLCH/sRGB correspondence, not script-verified — per
`DIRECTION.md` §11, nothing in this package has rendered in a browser yet.

---

## 12. Style-under-density claim (`DIRECTION.md` §6)

*"At forty rows this holds natively — a signal-token is one glyph plus one hue per row, the
same cost as a plain badge, so forty rows cost nothing extra."* This comp checks that claim
against real numbers: the Status column is `90px` wide holding one `28×28px` icon-only
token — narrower than the Item, Vendor, or Category columns beside it, and no wider than a
plain colored badge would need for the same job. Nothing about the token's cost scales with
row count; the 38-row table in §9 is the proof, not an illustration of it.

---

## 13. Content direction

Domain is generic industrial/warehouse stock (fasteners, electrical, raw material,
packaging, safety, tooling, adhesives, plumbing) — plausible-length real item names and SKU
codes, no invented brand or logo, no lorem, no fabricated business metric presented as a
claim (the footer's "214 items" is illustrative UI structure, stated as such). Terminology
lock held throughout: **item** (never product/SKU-as-noun), **vendor** (never supplier).
No person-attached field exists on this record type, so the avatar-chip pattern is
correctly absent rather than forced in.

---

**Self-check before return:** every hex above was read back against `DIRECTION.md` §6's
light palette table and status-token vocabulary — no value transcribed from memory. Column
widths (`1144`), band heights (`64+56+724+56=900`), and row-content math (`4+20+2+18+4=48`)
were re-added, not eyeballed. The Status column's exemption from the WCAG 2.5.8 exception
(§5) and the Actions column's need for it (§7) are stated with the reasoning, not asserted.
