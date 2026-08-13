# porcelain — 03 Items list — LIGHT

Canvas 1440×900. Composition anchor: **dense-grid**. Background mode: **flat-surface**.
HUMAN-APPROVED reference execution (gate-a-approved-porcelain.html lines 434–486). This file
MATCHES that frame at full spec resolution — refine, never redesign. All tokens/ratios from
`_register.md` §1–§5 (never re-derived).

## 1. Region map (x, y, w, h — sums checked)

| Region | x | y | w | h | Notes |
|---|---|---|---|---|---|
| Sidebar | 0 | 0 | 248 | 900 | card fill, 1px line right border (§3) |
| Main | 248 | 0 | 1192 | 900 | bg fill, pad 28px 36px → content x 284–1404 (1120w) |
| Breadcrumb | 284 | 28 | 1120 | 16 | mb 10 |
| Page head | 284 | 54 | 1120 | 49 | mb 24; controls 38h, vertically centered (top ≈ 60) |
| Filter row | 284 | 127 | 1120 | 30 | mb 14 |
| Table panel | 284 | 171 | 1120 | 512 | see §3 anatomy |
| Pagination | 284 | 695 | 1120 | 17 | mt 12 |
| Slack | 284 | 712 | 1120 | 160 | designed whitespace — this IS the sparse page |

Horizontal: 248 + 36 + 1120 + 36 = 1440 ✓
Vertical: 28+16+10+49+24+30+14+512+12+17+160+28 = 900 ✓

## 2. Chrome (shared verbatim with 02/06 — keep exact)

- **Sidebar** per §3: workspace switcher (mark "A", name "Atlas", sub "Acme Co.", chevron);
  seclabel "Main menu"; nav rows Dashboard / **Items (active, count 214)** / Purchase
  orders 18 / Sales orders 27 / Finance / HR; user card "Amira K." "Buyer · Procurement",
  avatar "AK".
- **Breadcrumb**: `Inventory / Items` — 12px ink2, current segment "Items" ink /500.
- **Page head**: h1 "Items" 22px/650 −0.01em lh28; sub "214 items across 4 warehouses"
  13px ink2, mt 3. Right cluster, gap 10: searchfield (h38 w260, 1px line border, r10, card
  fill, 15px search icon, placeholder "Search items…" 13px ink2, trailing ⌘K kbd chip 22px
  min r6) + ink button "New item" (h38 visual, pad 0 16px, ink fill, r10, 13px/550 white,
  15px plus icon gap 8; hit target extended to 44px per §3 policy). New item → surface 05.
- **Filter row**, gap 8: chip `Category: Fasteners ✕` + chip `Status: Low stock ✕` (h30,
  r-full, acc-t fill, acc 12.5px; ✕ dismiss accessible name "Remove filter: Category
  Fasteners" / "Remove filter: Status Low stock", ✕ hit ≥24×24) + ghost text button
  `+ Add filter` 13px acc, self-center.

Kept verbatim from the approved frame (MATCH rule wins; flagged, not fixed): the visible
rows span more categories/statuses than the active chips imply, and the count reads 214
with filters on. Surface 06 specs the honest filtered-to-zero sibling of this chrome.

## 3. Table panel — anatomy and column arithmetic

Panel: card fill, r14, 1px line border, shadow token, **padding 4px 14px** (approved
override of the 18px panel default). Table `width:100%`, border-collapse.

**Inner width**: 1120 − (2×1 border) − (2×14 padding) = **1090px** (border-box).

| # | Column | Width | Align | Content spec |
|---|---|---|---|---|
| 1 | select | 30 | center | 16×16 checkbox, r4, 1.5px ink2 border (line is decorative-only, never a control boundary — ink2 vs card 5.15 clears 3:1 non-text); checked = ink fill + white check (white on ink 17.74, same pair as ink button); hit area 24×24 min |
| 2 | Item | 320 | left | two-line cell, see row anatomy |
| 3 | Category | 130 | left | 13px/450 ink |
| 4 | Qty on hand | 105 | right | 13px/450 tnum ink |
| 5 | Reorder pt | 105 | right | 13px/450 tnum ink2 |
| 6 | Vendor | 210 | left | 13px/450 ink |
| 7 | Status | 150 | left | status pill per §3 register |
| 8 | actions | 40 | center | ⋯ per-row menu button |

Sum: 30 + 320 + 130 + 105 + 105 + 210 + 150 + 40 = **1090** ✓
Cell padding (within column widths): th 8px 10px, td 11px 10px.

**Row anatomy (default density)** — two-line Item cell:
name 13px/600 lh **20** + identifier 11px JetBrains Mono /500 ink2 lh **16** → content 36;
+ 11 top + 11 bottom padding = **58px**; + 1px line bottom border = **59px per row**
(last row: no border → 58). Single-line cells vertically centered.

Header row: 10.5px/600 mono-caps ink2, lh 14 + 8+8 pad + 1px border = **31px**.
Rows: 7×59 + 58 = 471. Panel height: 31 + 471 + (2×4 pad) + (2×1 border) = **512** ✓

**The 8 rows — exact, from the approved frame:**

| Item / identifier | Category | Qty | Reorder | Vendor | Status pill |
|---|---|---|---|---|---|
| Hex Bolt M6×20 · ITM-BOLT-M6X20 | Fasteners | 1,240 | 300 | Acme Fastening | ok · In stock |
| Hex Bolt M8×25 · ITM-BOLT-M8X25 | Fasteners | 86 | 150 | Acme Fastening | warn · Low stock |
| Terminal Block 6-Pos · ITM-TERM-6POS | Electrical | 0 | 60 | Voltix | mute · Draft |
| Copper Bar 2in · ITM-CUBAR-2IN | Raw material | 0 | 20 | Meridian Metals | bad · Out of stock |
| Safety Glasses, Clear · ITM-SAFE-GLASS | Safety | 480 | 100 | Guardian Safety | ok · In stock |
| Digital Caliper 6in · ITM-CAL-6IN | Tooling | 4 | 8 | Precision Tool | warn · Low stock |
| Epoxy Resin, 1L · ITM-EPOX-1L | Adhesives | 90 | 40 | BondTech | ok · In stock |
| Ball Valve 1/2in · ITM-VALV-BALL | Plumbing | 38 | 40 | FlowLine | warn · Low stock |

Pills exactly per register §3: h24 r-full pad 0 10px 12px/500, 7px currentColor dot gap 5;
ok=In stock, warn=Low stock, bad=Out of stock; **mute=Draft**: transparent fill, 1px
dashed line border, ink2 text, no dot. Dot + label always — never color alone. Rule made
explicit: Draft supersedes stock status (Terminal Block qty 0 shows Draft, not Out of
stock) — an unpublished item reports no stock state.

**Row actions**: one ⋯ icon button per row, 28×28 visual centered in the 40px column,
hit target 40×40 (row is 58h). Accessible name per record: "More actions for
ITM-BOLT-M6X20" (never bare "More"). Menu: Open · Edit · Duplicate · Change status ·
Delete. If this ever becomes an icon cluster, WCAG 2.5.8 spacing exception applies:
≥24px centre-to-centre.

**Sort affordance**: columns 2–7 sortable. Each th wraps its label in a button filling the
cell; 10px ▲/▼ indicator, acc on the actively-sorted column, ink2 on hover/focus of idle
columns, hidden otherwise — the approved frame shows server-default order (no sort param),
so no indicator renders, which is why MATCH holds. `aria-sort` on the active th only.
State lives in the URL: `/inventory/items?category=fasteners&status=low_stock&sort=&cursor=`
— sort e.g. `item.asc`; cursor carries list position (cursor pagination per API rules),
page numbers in the pagination row are derived display.

**Hover row**: fill `color-mix(in srgb, acc-t 45%, card)` — pointer cue only, never the
sole affordance. **Selected row**: full acc-t fill + checkbox checked; text stays ink
(pair not tabulated in §1 — flagged in §9, not re-derived).

## 4. Pagination + density

Row: 12.5px ink2. Left: "Showing 1–8 of 214" + **density toggle** (extension — §5 register
requires it to exist; not in the approved frame, so it lives here in table-owned chrome
that surface 06 omits at zero rows): icon-only, 28×28 visual / 40×40 hit, `aria-pressed`,
accessible name "Compact density". Right: `Prev · 1 2 3 … 27 · Next` — current page 1 ink
/600, others ink2; Prev disabled on page 1 (55% opacity + no pointer affordance, §1
disabled rule); each link ≥24×24 hit, ≥24px centre-to-centre.

**Compact density changes exactly this**: identifier inlines after the name (11px mono
ink2, 8px gap) → single-line cell lh 20; td pad 11→8 → row 36 + 1 border = **37px ≥ 36 ✓**.
Page-level controls unchanged (≥40px); in-row targets fall to the 2.5.8 exception (≥24px
centre-to-centre). Nothing else moves.

**The 40-row claim (sparse vs dense)**: this comp is the sparse page. At 40 rows nothing
changes but scroll — same columns, same widths, same chrome. Default density: 40×59−1 =
2,359px of rows → panel ≈ 2,400, document scrolls vertically; thead goes
`position:sticky; top:0`, card fill, keeps its 1px bottom hairline. Compact: 40×37−1 =
1,479 → panel ≈ 1,520. Pagination stays below the panel in both.

## 5. States owed

**(a) Loading** — skeleton, never a spinner (§3 register). Header row renders real column
labels immediately. 8 skeleton rows at exact final geometry (58px, same column widths,
same 11px cell padding), line-token blocks r6: select 16×16; Item 150×12 over 96×9 (gap 4);
Category 70×10; Qty 44×10 right; Reorder 32×10 right; Vendor 96×10; Status 84×18; actions
20×10. Shimmer only when motion allowed (§5); static blocks under reduced motion.
Pagination text hidden until the count arrives; its 17px height stays reserved — zero shift.

**(b) Sparse vs dense** — designed above (§4): 8 rows leaves 160px slack below pagination;
40 rows scrolls with sticky thead. Identical spec otherwise, stated concretely there.

**(c) Single row selected** — Space (or checkbox) on Hex Bolt M8×25: row acc-t fill,
checkbox ink-filled. **Selection action bar** appears in-flow inside the panel above thead:
h 44, r10, acc-t fill, margin 6px 0 4px; left "1 selected" 13px/550 acc; right: text
buttons **Change status** · **Export** (13px/550 acc, hit 40px, gap 16) + ✕ "Clear
selection" (24×24 hit). Panel grows 512→566, pagination shifts to y 749 — in-flow, no
overlay (glass is reserved for the ⌘K palette only). Polite live region: "1 row selected."
Header checkbox: `aria-label` "Select all items on this page", mixed state when partial.

Zero-results state is NOT this surface — it is surface 06, from this same chrome.

## 6. Type (all from §2; deltas only)

Roles used: h1, body/table 13/450 lh20, sub/meta, delta/fine, pill 12/500, mono-caps th,
identifier 11 mono, kbd chip. **Deltas**: item name 13px/**600** lh 20 (the approved
frame's `<b>`, pinned to the register's 600 name-weight as on user-card/ws names);
identifier lh pinned to 16 for the row-height math; pagination current-page /600.
Tabular-nums on Qty and Reorder cells.

## 7. Palette pairs used (§1 verified ratios only)

| Pair | Ratio |
|---|---|
| ink on bg (h1, crumb current) | 16.57 |
| ink2 on bg (crumb, sub, pagination) | 4.81 |
| ink on card (table cells, chrome) | 17.74 |
| ink2 on card (th, identifiers, Reorder col, placeholder, Draft pill text) | 5.15 |
| white on ink (New item button, checked checkbox) | 17.74 |
| acc on acc-t (filter chips, selection bar, active nav) | 4.58 |
| acc on bg (+ Add filter, focus ring — ring floor 3.0) | 4.86 |
| acc vs card, non-text (sort indicator, checked fill — floor 3.0) | 5.20 |
| ok-tx on ok-bg (In stock) | 4.80 |
| warn-tx′ #94650c on warn-bg (Low stock — FINAL adjusted value) | 4.54 |
| bad-tx on bad-bg (Out of stock) | 5.25 |
| line | decorative only — never the sole boundary/state signal |

## 8. Accessibility (this surface)

- Skip link first, targets `#main-content`; one h1 ("Items"), one main, one
  `nav aria-label="Primary"`; SPA route change → focus h1 (`tabindex="-1"`).
- Table is `role="grid"`, `aria-rowcount="215"` (header + 214), `aria-rowindex` 2–9 on
  visible rows. **Roving tabindex** — one tab stop for the whole grid. Arrows move cell
  focus; Home/End = row edges; Ctrl+Home = first cell of first row; **Enter** opens the
  item's detail record; **Esc** from an embedded widget (checkbox, ⋯ menu) restores grid
  navigation; **Space** selects the row; **Shift+arrows** extend selection contiguously.
- Selection surfaces the action bar (§5c) with polite live-region count announcements.
- **Focus after delete**: focus moves to the row now occupying the deleted index (i.e. the
  next row), previous row if the last was deleted, table container if the grid empties.
- Icon-only controls carry per-record names: "More actions for ITM-…", "Remove filter: …",
  "Clear selection", "Compact density".
- Targets: page controls ≥44 (extended hit per §3 policy); in-row/pagination controls
  ≥24×24 under 2.5.8, clusters ≥24px centre-to-centre.
- Focus ring 2px solid acc, 2px offset, `:focus-visible` only (verified vs bg/card/acc-t).
- Sort + filters + cursor in URL → state survives reload and is shareable; filter changes
  announced politely via the count line.
- Reduced motion: skeleton shimmer → static. No parallax.

## 9. Self-check

Sums re-added: 30+320+130+105+105+210+150+40=1090 = 1120−2−28 ✓; rows 7×59+58=471, panel
31+471+8+2=512 ✓; vertical 28+16+10+49+24+30+14+512+12+17+160+28=900 ✓. Tokens read back
against §1/§2/§3: warn-tx′ #94650c (not the superseded #96660f), mute pill dashed-line +
ink2 + no dot, ⌘K glass untouched by this surface. Flagged, not resolved: (1) ink-on-acc-t
(selected row text) has no §1 ratio — visibly far above floor but unverified; conductor may
want it added to the register; (2) approved frame's filter-chips/row-data mismatch kept
verbatim per MATCH; (3) density toggle is the one element not in the approved frame,
required by §5 register, placed in table-owned pagination chrome so 06 is unaffected.
