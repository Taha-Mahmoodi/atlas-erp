# the yard: Surface 4 of 7 — Vendor Bill Detail

**Coded-comp mode — LIGHT.** Canvas: 1440×900 fixed desktop viewport, full chrome, web/desktop-only
(no platform mode; `DIRECTION.md` §2). No image generated.

## 0. Job

Lets an AP clerk confirm one vendor bill is safe to leave posted (or safe to void) by putting its
predecessor/successor chain — PO → GRN → this Bill (Atlas's real document-flow architecture,
`CLAUDE.md` §"Architecture rules" 2) — next to the line items it decomposes, and by giving the
screen the one thing the live app currently lacks: a way back to the list it came from. Real record,
pulled from `shots/current/detail-vendor-bill.png` + `list-vendor-bills.png`, not invented:
**BILL-2026-00003**, vendor **Acme Supplies Co**, vendor's reference **INV-260615**, bill date
**Jun 20, 2026**, due **Jul 20, 2026**, gross / open **USD 54.00**, status **POSTED**.

## 1. Layout move — exact numbers

Chrome shared with the rest of the shell (survival-list item, not reinvented here):

| Region | Box | Notes |
|---|---|---|
| Global top bar | `0,0` → `1440×56` | `space-sticky` token (56px, `ACCESS.md` §13 row 5 for this concept) |
| Left nav rail | `0,56` → `240×844` | icon+label at rest — 1440 is below the 1600px reveal breakpoint, so this is the base state, not the widened one |
| Content column | `240,56` → `1200×844` | 32px padding all sides → **1136×780 content well** at `272,88` |

**Defect fix, first thing in the well:** `nav aria-label="Breadcrumb"` at `272,88` → `1136×24`.
`Finance / Vendor Bills / BILL-2026-00003` — first two segments are real links (accent-ink,
underline on hover, visible focus ring), separator "/" in text-secondary, current segment in
text-primary with `aria-current="page"`. This is the confirmed-defect fix: the live screen has
neither a breadcrumb nor a back link today: this one renders before the title, not after it.

Content well, top to bottom (8px base unit governs every gap; 44px control-floor heights are the
one deliberate exception to the grid, per `ACCESS.md` §13 row 1):

| Element | Box | Height math |
|---|---|---|
| Breadcrumb | `272,88` → `1136×24` | — |
| *(gap 24)* | | |
| Title row | `272,136` → `1136×44` | 44px = control floor, holds H1 + status token + actions |
| *(gap 24)* | | |
| Main record card | `272,204` → `760×440` | see below |
| Flow-strip card | `1064,204` → `344×482` | see below |

Two cards, unequal size, sitting on bare substrate — the collision's structural half made literal:
Bento states importance by card size, and exactly two cards exist on this screen, not a card per
field. Both share `radius-card: 16px`, `shadow-card: 0 1px 2px oklch(0 0 0 / 0.05), 0 6px 16px
oklch(0 0 0 / 0.08)` (soft, no blur/backdrop — no glass anywhere on this screen). Card bottoms:
main `204+440=644`, flow-strip `204+482=686`; well bottom `88+780=868` — both clear it (182px /
182px margin below main, no scroll forced on either card at this record's real content length).

**Main record card** (760×440, 24px internal padding → 712px inner width):
- Header-field grid, 96px tall, 3 cols × `(712−64)/3=216px` (2×32 gutters), 2 rows (label
  12/16 + 4px gap + value 14/20 = 40px/row, 16px row-gap → 40+16+40=96):
  Row 1 — Vendor `Acme Supplies Co` / Vendor's reference `INV-260615` / Bill date `Jun 20, 2026`.
  Row 2 — Due date `Jul 20, 2026` / Open amount `USD 54.00` (tabular-nums) / Payment terms `Net 30`
  (placeholder field, plausible ERP length, not presented as a claim).
- *(gap 32)*
- Line-items grid, `role="grid"`, 712px wide, header row **56px** (reuses `space-sticky`, sticky-
  capable though this record's 3 rows never force scroll) + 3 body rows × 40px = `56+120=176`,
  hairline divider, then a 3-row summary block (`16px top pad + 3×24px rows = 88`). Total
  `176+88=264`. Card total: `24+96+32+264+24=440` ✓.
  Columns (sum 712): `ACCOUNT 160 | DESCRIPTION 220 | QTY 60 | UNIT PRICE 100 | NET 90 | TAX 82`.
  QTY/UNIT PRICE/NET/TAX right-aligned, tabular-nums, decimal-aligned. Rows (real total `USD 54.00`
  decomposed into plausible catalog items — the total is real, the split is placeholder, stated
  once here and not repeated as if it were sourced):

  | Account | Description | Qty | Unit price | Net | Tax |
  |---|---|---|---|---|---|
  | 2100 — GR/IR Clearing | Steel Bolt M6 | 200 | USD 0.12 | USD 24.00 | — |
  | 2100 — GR/IR Clearing | Plastic Casing | 60 | USD 0.30 | USD 18.00 | — |
  | 2100 — GR/IR Clearing | Cable Tie 200mm | 400 | USD 0.03 | USD 12.00 | — |

  Summary: Subtotal `USD 54.00` / Tax `—` / **Gross total `USD 54.00`** (bold, tabular-nums,
  matches the real Open amount — this bill is fully unpaid).

**Flow-strip card** (344×482, 24px internal padding → 296px inner width): eyebrow `DOCUMENT FLOW`
(16px) + 16px gap, vertical hairline connector at `x=20` (inset from card padding), 3 stage rows on
it, each with a 10px marker dot at the connector, 24px gap between rows. Per-row height `118px`
(eyebrow 16 + 4 gap + mono id 18 + 8 gap + status token 24 + 8 gap + avatar-chip row 20 + 4 gap +
date line 16). `24 pad + 16 + 16 + 118 + 24 + 118 + 24 + 118 + 24 pad = 482` ✓. Full detail in §4.

## 2. Type table

| Role | Face | Size / weight | Line-height | Used for |
|---|---|---|---|---|
| title-mono | JetBrains Mono Variable | 20px / 600 | 24px | H1 identifier portion only — `BILL-2026-00003`. The one place mono is set at title size, because the title *is* an identifier |
| title (prose) | Inter Variable | 20px / 600 | 24px | "Vendor Bill" prefix in the H1, set immediately before the mono run |
| section-eyebrow | Inter Variable | 12px / 450, caps, +0.03em | 16px | ACCOUNT/DESCRIPTION/QTY/UNIT PRICE/NET/TAX, field labels, `DOCUMENT FLOW`, stage doc-type labels |
| body/data | Inter Variable | 14px / 450 | 20px | field values, item descriptions, breadcrumb link text |
| body/data · tabular-nums | Inter Variable, `font-variant-numeric: tabular-nums` | 14px / 450 | 20px | QTY, UNIT PRICE, NET, TAX, Open amount, Subtotal/Gross total |
| meta | Inter Variable | 12px / 450 | 16px | breadcrumb separators, avatar-chip names, checked-by/date stamp lines |
| mono-identifier | JetBrains Mono Variable | 13px / 500 | 18px | `PO-2026-00014`, `GRN-2026-00019`, `BILL-2026-00003` inside the flow-strip |
| button-emphasis | Inter Variable | 16px / 600 | 20px | **Approve** label only — `ACCESS.md` §13 row 3 requires accent-emphasis text at ≥16px/600 |
| button | Inter Variable | 14px / 500 | 20px | Void, Cancel, and all other control labels |

## 3. Palette, paired, with ratios

Given (dispatch palette, restated for this surface, not recomputed):

| Pair | Values | Ratio |
|---|---|---|
| text-primary / substrate | `oklch(0.21 0.015 290)` / `oklch(0.985 0.004 290)` | ~15:1 |
| text-primary / card | `oklch(0.21 0.015 290)` / `oklch(1 0 0)` | ~16:1 |
| text-secondary / card | `oklch(0.46 0.02 290)` / `oklch(1 0 0)` | ~6.5:1 |
| accent-ink / card or substrate | `oklch(0.44 0.15 290)` | ~7:1 — breadcrumb links, Void button text |
| accent-emphasis / white | `oklch(0.53 0.18 290)` / white | ~4.8:1 (unverified, RISK 4) — **Approve fill, 16px/600 only, per §2** |
| accent-tint / accent-ink | `oklch(0.94 0.035 290)` / `oklch(0.44 0.15 290)` | ~6:1 — current-stage row highlight in the flow-strip |
| hairline | `oklch(0.89 0.01 290)` | decorative-only, sub-3:1, never the sole divider signal (used only alongside the connector dots and row spacing, which carry structure independently) |

Status-token pairs (given, restated — see §4 for which state is used where on this screen):

| State | Fill / text | Ratio note |
|---|---|---|
| Closed (PO row) | `oklch(0.35 0.008 290)` / white | dark-neutral-reversed, high contrast |
| Posted/Approved (GRN row, Bill row, title chip) | `oklch(0.58 0.15 150)` / `oklch(0.18 0.03 150)` | ~4.9:1 est. |
| Overdue/Error (modal destructive confirm only) | `oklch(0.55 0.19 25)` / white | ~4.9:1 est. |

Disabled Approve (this record's actual state — already POSTED, nothing to approve): fill
`oklch(0.93 0.006 290)`, text `oklch(0.55 0.02 290)`, `aria-disabled="true"`. Disabled controls are
WCAG-exempt from the contrast floor; stated for completeness, not claimed as passing.

## 4. The flow strip — the signature move

Three rows on one connector, current document visually distinct, every row carrying a real
person-attached checked-by as an avatar-chip (20px circle, initials, neutral tint —
`oklch(0.94 0.035 290)` bg / accent-ink text) per the concept's own avatar-chip rule for any
person-attached record. No invented photo anywhere (`§14`) — initials only.

1. **PURCHASE ORDER** · `PO-2026-00007` · token **Closed** (lock glyph) · avatar-chip "MR" **M.
   Reyes** — Procurement · Issued May 20, 2026
2. **GOODS RECEIPT** · `GRN-2026-00011` · token **Approved** (check glyph, Posted/Approved fill) ·
   avatar-chip "TO" **T. Okafor** — Warehouse · Received Jun 15, 2026
3. **VENDOR BILL** *(current — `accent-tint` row fill, 2px accent-ink left border)* ·
   `BILL-2026-00003` · token **Posted** (check glyph, same Posted/Approved fill) · neutral system
   chip (gear glyph, not an avatar — no person checked this one) **System** — 3-way match ·
   Posted Jun 20, 2026

Every token gets a real accessible name, per `ACCESS.md` §13 row 10's pattern:

- Title-row chip: `"Posted — Vendor Bill BILL-2026-00003, posted Jun 20, 2026"`
- PO row: `"Closed — Purchase Order PO-2026-00007, checked May 20, 2026 by M. Reyes"`
- GRN row: `"Approved — Goods Receipt GRN-2026-00011, checked Jun 15, 2026 by T. Okafor"`
- Bill row: `"Posted — Vendor Bill BILL-2026-00003, checked Jun 20, 2026 by system 3-way match"`

Reused PO/GRN numbers (`PO-2026-00007` / `GRN-2026-00011`) — chosen to match the seed screenshot's
own numbering pattern (`BILL-2026-00003`, sequential per module), not invented arbitrarily.

## 5. Primary actions and the modal

Title row, right-aligned: **Approve** (accent-emphasis fill, 16/600, `aria-disabled="true"` on this
record — already Posted, nothing to approve, `title="Already posted"`) and **Void** (outline,
accent-ink text 14/500, enabled — a posted bill can still be voided). Both 44px tall, `radius-
control: 10px`, 20px horizontal padding, 12px gap between them.

**Void** opens `role="dialog" aria-modal="true" aria-labelledby="void-title"`, 400px wide, centered,
`oklch(0 0 0 / 0.4)` scrim, `radius-card: 16px`, `shadow-card`, 32px internal padding:
- Title "Void this bill?" — 18/600.
- Body "BILL-2026-00003 will be marked void. This can't be undone." — 14/450, text-secondary,
  12px gap below title.
- Actions row, 24px gap above: **Cancel** (outline, left, **initial focus lands here** per the
  dispatch instruction — the least-destructive action, not the destructive one) and **Void bill**
  (fill `oklch(0.55 0.19 25)` / white, right). Focus trapped inside the dialog; `Esc` and Cancel are
  equivalent.

## 6. Content direction (one line)

Every field that traces to the real seed screenshot does exactly — `BILL-2026-00003`, Acme Supplies
Co, `INV-260615`, `USD 54.00`, Jun 20 / Jul 20 2026, status POSTED; the three line items decompose
that one real total into plausible catalog items at realistic qty/unit-price (never presented as
sourced data), and everything the seed data doesn't cover (PO/GRN numbers, checked-by names,
payment terms) is placeholder at realistic ERP-demo length.

## 7. Logged tokens

- **Composition anchor: `right-rail-caption`** — wide left field (record card) against a narrow
  right rail (flow-strip as inspector/detail), which is this concept's own opening-move description
  for record detail screens, not a neighbor-matching choice.
- **Background mode: `flat-surface`** — one solid substrate (`oklch(0.985 0.004 290)`), the two
  cards inline on it via `shadow-card` alone, no texture, no gradient, no image. This is the
  surface half of the collision made literal: Bento's cards carry all the visual structure, so the
  ground underneath stays deliberately quiet — a textured mesh would compete with the signal-tokens
  for attention, which the concept's "calm neutral until something needs a hand" rule argues against.
- **One line:** this is the one surface in the set built around a persistent right-rail inspector
  (items-list is `dense-grid`, role-home is a bento grid proper) — the flow-strip's two-card,
  one-connector shape is what makes it read differently from either neighbor.

## 8. Self-check (embarrassment gate)

- Arithmetic re-read against §1: `240+1200=1440` ✓, `1200−64=1136` ✓, `56+844=900` ✓,
  `272+1136=1408`, `1408+32=1440` ✓, `760+32+344=1136` ✓, main card `24+96+32+264+24=440` ✓,
  flow card `24+16+16+118×3+24×2+24=482` ✓, line-item columns `160+220+60+100+90+82=712` ✓,
  header-field cols `216×3+32×2=712` ✓, line total `24.00+18.00+12.00=54.00` ✓ matches gross.
- Contrast pairs re-read against §3: all named pairs clear their stated floor except accent-
  emphasis (flagged, size-gated per its own rule) and disabled Approve (flagged, exempt).
- Terminology lock held: `item` (line items), `vendor` (never supplier), no `product`/`SKU`
  anywhere.
- Defect fix present and first in tab order after the skip link: breadcrumb is the first element
  inside `<main>`, before the H1.
- Void modal's initial-focus-on-Cancel instruction is honored explicitly in §5, not left implicit.
- No fabricated data presented as insight: checked-by names, PO/GRN numbers, and payment terms are
  structural placeholders, stated as such once in §6, not repeated as if sourced.
- Would I put my name on this: yes.

## 9. Could not fully satisfy

The avatar-chip initials-plus-name wrap inside a 256px text column (`296 − 20 inset − 20 chip −
gap`) is specified as one line at 12px meta size; whether "M. Reyes" plus "— Procurement" on the
next line actually needs its own row or fits inline is a build-time wrap question the coded spec
states the budget for (256px, 12/16) but doesn't resolve to the character.
