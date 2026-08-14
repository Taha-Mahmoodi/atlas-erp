# 06 · Empty state (items list, filtered-empty) — LIGHT

Canvas 1440×900 · porcelain · anchor: **centered-statement** · background: **flat-surface**
This is surface 03's exact screen in its zero-result data state. All chrome below is copied
verbatim from the approved 03 frames (`gate-a-approved-porcelain.html` 434–485); only the
panel interior and the pagination row differ. The sibling 03 comp and this comp must diff
clean on chrome.

## 1. Region map (x, y, w, h — sums checked)

| Region | x | y | w | h | Note |
|---|---|---|---|---|---|
| Sidebar | 0 | 0 | 248 | 900 | identical to 03 |
| Main | 248 | 0 | 1192 | 900 | pad 28/36 → content x 284–1404 (1120) |
| Breadcrumb | 284 | 28 | 1120 | 16 | |
| Page head | 284 | 54 | 1120 | 48 | crumb + 10 |
| Filter chip row | 284 | 118 | 1120 | 30 | pagehead + 16 |
| Table panel | 284 | 162 | 1120 | 560 | chip row + 14 |
| Count line | 284 | 734 | 1120 | 18 | panel + 12 — replaces pagination |

Horizontal: 248 + 1192 = 1440 ✓ · 36 + 1120 + 36 = 1192 ✓
Vertical: 28+16+10+48+16+30+14+560+12+18 = 752 ≤ 872 (900 − 28 bottom pad) ✓
Panel height 560 is a **min-height**: it holds the footprint the populated table occupies,
so filtered→empty does not collapse the page under the user's pointer.

## 2. Chrome (verbatim from approved 03 — cite, don't redesign)

- **Sidebar** 248×900 per §3: workspace switcher (Atlas / Acme Co.), section label
  "Main menu", nav rows — Dashboard · **Items (active, acc-t fill, acc text, 550, badge
  214)** · Purchase orders 18 · Sales orders 27 · Finance · HR — user card Amira K.,
  Buyer · Procurement. Badge stays **214**: the sidebar counts the tenant, not the filter.
- **Breadcrumb**: `Inventory / Items` — 12px ink2, current segment ink /500.
- **Page head**: h1 "Items" (22px/650) + sub "214 items across 4 warehouses" (13px ink2 —
  stays; it is the truthful denominator for the statement below). Right: searchfield
  (h 38, w 260, 1px line, r10, card fill, 15px search icon, placeholder "Search items…"
  13px ink2, ⌘K kbd chip) + ink button "New item" (h 38 visual / 44 hit, pad 0 16px, r10,
  13px/550 white on ink). **If a query is present it persists in the field** — this state
  never wipes user input.
- **Filter chip row**: `Category: Fasteners ✕` · `Status: Low stock ✕` (h 30, r-full,
  acc-t fill, acc 12.5px, gap 8) + "+ Add filter" ghost text 13px acc. Chips stay visible
  and dismissible — they are the cause of the state and the fastest way out of it.

## 3. Panel interior (the only new region)

Panel: card fill, r14, 1px line border, shadow, **pad 4px 14px** (as approved 03).

- **thead kept**: the full 8-column header row (mono-caps 10.5px/600 ink2, th pad 8px 10px,
  1px line bottom), inner y 166–196. The header staying says "the table is still here —
  your filters emptied it," which is the entire message of this surface. Zero body rows.
- **Centered statement**, vertically centered in the remaining panel area (zone 196–718,
  h 522 → block ≈ y 402–512, h 110, horizontally centered, text-align center):
  - Line 1 — `No items match these filters.` — Inter 15px/500, ink, lh 22.
  - Line 2 — `214 items exist — the current filters hide all of them.` — 13px/450 ink2,
    lh 20, margin-top 6.
  - Button — `Clear filters` — **ink variant**, standalone 44px tall outright (§3 policy:
    empty-state CTAs are standalone primaries), pad 0 16px, r10, 13px/550 white on ink,
    margin-top 18. **Why ink, not chip**: clearing filters is the one action that resolves
    this state — 214 items are one click away. "New item" in the page head is chrome
    parity with 03, not this state's answer; creating a 215th item would not make it match
    `Status: Low stock`. The panel CTA is the semantic primary of the state.
    Clears **chips only** — the search query, if any, is untouched (it is user input, and
    it may be the filter the user wants kept).
- NO illustration, no mascot, no icon above the statement. Porcelain empties are
  typographic and calm.

## 4. Count line (replaces pagination)

`0 of 214 shown` — 12.5px ink2 on bg, left-aligned where "Showing 1–8 of 214" sits in 03.
The Prev/pages/Next cluster is **absent** — there is nothing to page.

## 5. Data states this surface owes

**(a) FILTERED-EMPTY** — everything above. Filters hide everything that exists.

**(b) TRUE-EMPTY variant** — zero items exist in the tenant:

| | Filtered-empty | True-empty |
|---|---|---|
| Chip row | present, dismissible | **absent** — no filter can exist |
| Searchfield | present, keeps query | **absent** — nothing to search |
| Pagehead controls | search + New item (chrome parity) | **empty** — the panel CTA is the only "New item"; two identically named primaries would be a duplicate accessible name |
| Pagehead sub | "214 items across 4 warehouses" | "0 items" |
| Sidebar Items badge | 214 | absent (no count to show) |
| Statement line 1 | "No items match these filters." | `No items yet.` |
| Statement line 2 | "214 items exist — the current filters hide all of them." | `Add your first item to start tracking stock.` |
| CTA | Clear filters (ink, 44px) | `New item` (ink, 44px, 15px plus icon) |
| Count line | "0 of 214 shown" | absent — no denominator exists |
| thead | kept | kept — the columns preview what the data will look like |

**Why the CTA differs**: filtered-empty is a full tenant seen through a too-narrow lens —
the productive route is *clearing* (restore what exists). True-empty is an actually empty
tenant — the only route is *creating*. Same geometry, opposite verbs; the copy states the
cause ("filters hide" vs "no items yet") so the user never confuses one for the other.
Layout is identical: same panel, same centered block, same y positions. Register note: this
surface **invites** ("Add your first item…"); it never apologizes — apology language belongs
to the 07 error sibling, and none appears here.

## 6. Type — deltas from §2 only

One delta: **empty-statement** — Inter Variable 15px/500, lh 22, ink. Sits between body
(13/450) and h1 (22/650); the state's one line of voice, dispatched as part of this
surface's brief. Everything else cites §2 verbatim: h1, sub/meta, nav, mono-caps th,
body 13, kbd chip, pill (unused here — no rows).

## 7. Palette pairs used (§1 verified ratios — cited, not re-derived)

| Pair | Ratio |
|---|---|
| ink on card (statement line 1, thead context) | 17.74 |
| ink2 on card (statement line 2, th, placeholder) | 5.15 |
| ink on bg (crumb current, h1) | 16.57 |
| ink2 on bg (crumb, pagehead sub, count line) | 4.81 |
| acc on bg ("+ Add filter", focus ring vs bg) | 4.86 |
| acc on acc-t (filter chips, active nav) | 4.58 |
| white on ink (both ink buttons) | 17.74 |
| line | decorative only (1.21 vs card) — never the sole boundary |

## 8. Accessibility

- Transition into zero results announces via the **polite** live region: "0 items match" —
  polite, not assertive: an empty result is information, not an emergency (§5).
- Chips are `<button>`s, accessible names "Remove filter: Category — Fasteners" /
  "Remove filter: Status — Low stock". Enter/Space activate. **No Esc binding on chips** —
  Esc is reserved for grid-nav restore and palette close (§3/§5); overloading it here would
  make Esc ambiguous. On removal, focus moves to the next chip, or to "+ Add filter" if it
  was the last.
- **"Clear filters" focus**: on activation the button leaves the DOM with the empty state,
  so focus moves to the **first row of the repopulated grid** (the roving-tabindex entry
  point, per §5's deleted-row convention: nearest meaningful content). Live region
  announces "Showing 1–8 of 214".
- The grid keeps `role="grid"` with its header row and zero data rows; the statement block
  is a sibling of the table inside the panel, plain content — not an alert, not a dialog.
- Skip link, one h1, one main, one nav per §5. 44px targets: chips are 30px visual with
  hit-target extended to 44px (§3 hit-area policy); the CTA is 44px outright.
- True-empty: live region "0 items"; initial focus follows normal route-change rule
  (h1, tabindex −1).

## 9. Self-check

Sums re-added (§1 table: 752 ≤ 872, widths 1440/1192 ✓). All hexes and ratios read back
against `_register.md` §1 — no re-derived values; 15px/500 confirmed as the single §2
delta; chip/searchfield/pagehead values re-read against approved frame lines 453–465;
anchor + background tokens confirmed against the §6 closed menus.
