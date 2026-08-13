# 04 — Vendor bill detail · porcelain · LIGHT · 1440×900

Composition anchor: **right-rail-caption** · Background mode: **flat-surface**
The run's only right-rail surface. Users arrive from the 03 vendor-bills list (dense-grid);
this screen trades the grid for a wide working column + narrow caption rail. Same shell,
same components, no invention — everything below cites `_register.md`.

## 2. Region map (x, y, w, h — sums checked in §9)

| Region | x | y | w | h |
|---|---|---|---|---|
| Sidebar (§3 sidebar, Finance active) | 0 | 0 | 248 | 900 |
| Main region (pad 28/36 → content 284–1404 × 28–872) | 248 | 0 | 1192 | 900 |
| Breadcrumb | 284 | 28 | 1120 | 16 |
| Page head | 284 | 56 | 1120 | 50 |
| Notice line (status-dependent, drawn: Posted) | 284 | 112 | 1120 | 16 |
| Main column — line-items panel | 284 | 144 | 764 | 182 |
| Right rail — meta card | 1064 | 144 | 340 | 354 |
| Right rail — document-flow panel | 1064 | 514 | 340 | 226 |

Main column 764 + gap 16 + rail 340 = 1120. Rail right edge 1064+340 = 1404 = content edge.
When the notice line is absent (Draft), the two columns rise to y=128; the comp is drawn in
the Posted state, matching the live screen.

## 3. Per-region spec

**Sidebar / workspace switcher / user card** — §3 verbatim, Finance nav row active
(acc-t fill, acc text, 550).

**Breadcrumb** — 12px ink2: `Finance / Vendor bills / ` + current segment `BILL-2026-00003`
in ink /500, identifier face (§2 identifier at breadcrumb size stays 12px Inter — only the
current segment; mono is reserved for the h1 and data identifiers to keep one mono moment
per band).

**Page head** — the h1 IS the identifier, so the mono-h1 decision is stated here and in §6:
the h1 slot keeps §2's h1 line box (lh 28) so pagehead geometry never changes, but the text
renders in **JetBrains Mono Variable 20px/600, lh 28, normal tracking** — the §2 identifier
role promoted to title scale. Mono at 20px matches Inter 22px optically (wider set, taller
x-height); Inter's −0.01em is dropped because mono is fixed-pitch. If a future title ever
mixes words and a code, the words are Inter 22px/650 and the code is a 20px/600 mono span
on the same baseline. Beside the h1, 10px gap, baseline-centred: **status pill** (§3).
Sub line: 13px ink2 — `Acme Supplies Co · due Jul 20, 2026`.
Controls right (10px gap, centred on the h1 row): **only** the ink button `Post bill`,
38px visual / 44px hit (§3 policy), rendered **only when status = Draft AND the viewer
holds `finance.ap.manage`**. Pending: label becomes `Posting…`, disabled treatment per §1
note (ink2 @55%, border emphasis and pointer dropped), `aria-disabled`, polite live-region
announce on completion. In the drawn Posted state the control slot is empty — no dead
buttons.

**Status pill mapping** (label, never hue, is the discriminator — Posted and Paid share the
ok variant deliberately; the dot+label rule in §3 already forbids colour-alone):

| Status | Pill variant (§3) |
|---|---|
| Draft | mute — transparent fill, 1px dashed line border, ink2 text, no dot |
| Posted | ok |
| Partially paid | warn |
| Paid | ok |
| Reversed | bad |

**Notice line** — 12px ink2, one line, shown on every posted-side status (Posted /
Partially paid / Paid / Reversed): `Posted bills are immutable — corrections post a
reversing entry.` (state d). On Draft without permission this row instead carries the
permission line (state c). On Draft with permission the row is absent.

**Line-items panel** (764×182) — §3 panel: card, r14, 1px line border, shadow, pad 18.
Panel head: mono-caps label `LINE ITEMS` left; right meta 12px ink2 `1 line`.
Table (§3 table), inner width 728, columns:

| Account 240 | Description 268 | Net 140 (right, tnum) | Tax 80 (right, tnum) |

th mono-caps 10.5px ink2, pad 8/10, 1px line bottom (row h 31). td 13px ink, pad 11/10,
1px line bottom (row h 43). One data row: `2100 — GR/IR Clearing` · `GR/IR clearing` ·
`USD 54.00` · `—` (em-dash is the app's universal empty value; account labels are always
"code — name", the code is not split into a mono sub-line here because code+name is one
label). Footer row (h 42, no bottom border): `Gross total` 13px/500 ink2 right-aligned in
the Description cell, `USD 54.00` 13px/600 tnum right-aligned in Net, Tax cell empty.
Money everywhere in this format, right-aligned, tabular-nums.

**Meta card** (340×354) — §3 panel. Head: mono-caps `BILL` left. Body: single-column `dl`,
6 fields, this order, each dt mono-caps 10.5px ink2 (lh 14) + 4px + dd 13px/450 ink
(lh 20), 12px between fields:

1. VENDOR — `Acme Supplies Co`
2. STATUS — status pill (same instance vocabulary as the h1 pill)
3. VENDOR'S REFERENCE — `INV-260615` (§2 identifier: mono 11px/500)
4. BILL DATE — `Jun 20, 2026`
5. DUE DATE — `Jul 20, 2026`
6. OPEN AMOUNT — `USD 54.00`, 13px/600 tnum (the one operative number; stated delta §6)

**Document-flow panel** (340×226) — §3 panel. Head: mono-caps `DOCUMENT FLOW` left.
The backend records predecessor/successor links for every document (PO → receipt → bill →
payment) and the architecture promises the UI can render the full chain; **the live page
does not render it yet — this panel closes that measured gap using only register parts.**
Plain vertical linked list (`<ol>`): a 16px left gutter carries a 7px currentColor dot per
row (line token for other documents, acc for the current one) joined by a 1px line-token
vertical rule — decorative, per §1 the rule is never the sole signal; order and labels
carry the sequence. Each stage row, h 44, r9 hover (nav-row hover treatment):
identifier **mono 12px/550 ink** (stated delta §6) + date 11.5px ink2 on the second line,
status pill (that document's own vocabulary) right-aligned. Rows are links; the whole row
is the target, accessible name `Open PO-2026-00003` (per-record, §5). Current document:
acc dot, identifier in acc, `aria-current="page"`, not a link. Example chain (identifiers
come from the docflow API; these are plausible-shaped, not claims):

1. `PO-2026-00003` · Jun 12, 2026 · ok pill
2. `GR-2026-00005` · Jun 18, 2026 · ok pill
3. `BILL-2026-00003` · Jun 20, 2026 · ok pill `Posted` — **current**
4. terminal muted row, h 28, 12px ink2, no dot: `Payment · —` (open amount USD 54.00 —
   no successor exists yet; em-dash convention)

## 4. Content

All fields extracted from the live app; none invented. h1 `BILL-2026-00003`; sub
`Acme Supplies Co · due Jul 20, 2026`; the 6 meta fields, table row, and gross total
exactly as listed above. The only action in existence on this route is `Post bill`.

## 5. States owed

**(a) Loading** — §3 skeleton: line-token blocks at r6 matching this exact geometry —
h1 block 240×22, pill 72×24, sub 180×13; meta card with 6 label/value block pairs;
table with th row real (labels are static) and one 43px row block; doc-flow with 3 row
blocks. Shimmer only when motion is allowed. **Bounded by construction:** the fetch has
exactly two exits — data or error. Skeleton lifetime = query lifetime (TanStack Query,
its finite retry policy included); when the query settles rejected, this state is
*replaced* by state (b). The live page's forever-`Loading…` on error is the measured bug
this clause exists to kill; there is no third state and no timer heuristic.

**(b) Error / not-found** — the run's 07 error-surface pattern rendered inside this route:
shell, sidebar, and breadcrumb persist (the app did not crash; the document failed). The
two-column area is replaced by one §3 panel, 480px wide, centred in the content box at
y=144: heading 15px/600 ink, one plain sentence 13px ink —
not-found: `There is no bill BILL-2026-00003 in this workspace.`
load failure: `This bill could not be loaded.` + the API's actual error string beneath in
12px ink2, verbatim, never swallowed. One standalone chip button `Back to vendor bills`,
44px tall outright (§3 policy — not in a pagehead). Focus moves to the panel heading
(`tabindex="-1"`), per §5 route-change rule.

**(c) Permission denied** — Draft bill, viewer without `finance.ap.manage`: the Post bill
button is **absent** — never rendered disabled, never a dead control with no explanation.
The notice row (284,112) carries, 12px ink2:
`Posting requires finance.ap.manage — ask an admin.`
Everything else on the page is identical to Draft-with-permission.

**(d) Immutability** — designed into the notice line above: on every posted-side status
the 12px ink2 line `Posted bills are immutable — corrections post a reversing entry.`
sits under the pagehead. It is information, not a warning — no pill, no bad-tx.

**(e) Conflict** — a Draft edited elsewhere while open here. A §3 panel (764 wide)
inserts at the top of the main column (y=144; line-items panel drops to y=144+h+16),
`role="alert"`, focus moved into it (`tabindex="-1"` on the panel heading, §5 assertive
rule). Head: mono-caps label `EDIT CONFLICT` in bad-tx. Sentence 13px ink: `This bill was
changed by someone else while you were editing.` Below, both versions side by side —
two equal columns, gap 16, each headed `Your version` / `Their version` (12px/550 ink),
listing only the fields that differ as dt/dd pairs (same dl spec as the meta card),
differing values in ink at /550. Footer row, right-aligned: ink button `Keep mine` +
chip button `Keep theirs`, both 38px visual / 44px hit. Panel height content-driven,
~200px at two differing fields. No auto-merge, no silent overwrite.

## 6. Type — deltas from §2 (all else verbatim)

| Delta | Spec | Why |
|---|---|---|
| identifier-h1 | JetBrains Mono Variable 20px/600, lh 28, no tracking | §2 identifier promoted to title scale; keeps the §2 h1 line box so pagehead geometry is unchanged; mono 20px ≈ Inter 22px optically |
| doc-flow identifier | mono 12px/550 | row-primary text, one step above the 11px sub-line role |
| Open amount dd | 13px/600 tnum | the operative number on the surface |

## 7. Palette — pairs used (§1 verified ratios, transcribed not re-derived)

| Pair | Ratio |
|---|---|
| ink on bg | 16.57 |
| ink2 on bg | 4.81 |
| ink on card | 17.74 |
| ink2 on card | 5.15 |
| acc on card (doc-flow current id, panel-head links) | 5.20 |
| acc on acc-t (active nav) | 4.58 |
| white on ink (Post bill / Keep mine) | 17.74 |
| ok pill: ok-tx on ok-bg | 4.80 |
| warn pill: warn-tx′ #94650c on warn-bg | 4.54 |
| bad pill / EDIT CONFLICT label: bad-tx on bad-bg / bad-tx on card | 5.25 / 6.16 |
| focus ring acc vs bg | 4.86 (floor 3.0) |
| line | decorative only — never sole boundary or state signal |

## 8. Accessibility notes

- Skip link → `#main-content`; one h1 / one main / one `nav aria-label="Primary"` (§5).
- Route entry: focus to h1 (`tabindex="-1"`); error state redirects that to its panel
  heading; conflict moves focus + `role="alert"`.
- Line-items table is read-only → plain `<table>` semantics; the §5 grid pattern is for
  work lists and does not apply here. Empty Tax cell: `—` with visually-hidden `no tax`.
- Doc-flow is an `<ol>`; whole-row links with per-record names (`Open GR-2026-00005`);
  current row `aria-current="page"`, not a link; sequence carried by list order, never by
  the decorative connector rule.
- Pills always dot+label; Posted vs Paid distinguished by label text (both ok-green).
- `Post bill` → `Posting…`: `aria-disabled`, polite live region announces `Bill posted`
  (or routes to error, state b). Absence-with-explanation over disabled-without (state c).
- All targets ≥44px (button hit-areas, 44px doc-flow rows, 44px error CTA).

## 9. Self-check

Horizontal: 284+764+16+340 = 1404 = 284+1120 ✓. Vertical: 28+16=44, +12→56, +50=106,
+6→112, +16=128, +16→144; main col 144+182=326 ≤ 872 ✓; rail 144+354=498, +16→514,
+226=740 ≤ 872 ✓. Line-items panel: 18+16+14+31+43+42+18 = 182 ✓. Meta card:
18+16+14+(6×38+5×12=288)+18 = 354 ✓. Doc-flow: 18+16+14+(3×44)+28+18 = 226 ✓.
Tokens read back against `_register.md` §1–§3: warn-tx′ #94650c (final value), all ratios
transcribed from the verified table, no re-derivation. Anchor/background from the §6
closed menus: right-rail-caption · flat-surface.
