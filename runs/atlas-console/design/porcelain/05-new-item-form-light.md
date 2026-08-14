# porcelain — 05 New item form — LIGHT

Canvas 1440×900 (viewport; page height 1270, scrolls). Composition anchor: **stacked-center**.
Background mode: **flat-surface**. Extends the approved register (`_register.md`) — shell and
components verbatim from §3; nothing invented except the checkbox, specced below as a minimal
extension of the ink-button idiom.

**Panel decision (one line):** the form sits on a **card panel** — §1 verifies bad-tx (6.16),
helper ink2 (5.15) and every owed state against *card*, not bg, so the panel puts all
error/helper text on a verified substrate.

## 2. Region map @ 1440 wide

| Region | x | y | w | h | Check |
|---|---|---|---|---|---|
| Sidebar (shell, §3) | 0 | 0 | 248 | 900 | 0+248=248 ✓ |
| Main | 248 | 0 | 1192 | 1270 | 248+1192=1440 ✓ |
| Content area (pad 28/36) | 284 | 28 | 1120 | — | 284+1120=1404=1440−36 ✓ |
| Form column | 564 | 28 | 560 | — | 284+(1120−560)/2=564; 564+560=1124 ✓ |
| Breadcrumb | 564 | 28 | 560 | 16 | |
| h1 "New item" | 564 | 54 | 560 | 28 | crumb 44 + 10 gap = 54 ✓ |
| Card panel | 564 | 106 | 560 | 1128 | h1 82 + 24 = 106; 106+1128=1234 ✓ |
| Panel inner (pad 24) | 588 | 130 | 512 | 1080 | 24+1080+24=1128 ✓ |
| Actions row (in panel) | 588 | 1166 | 512 | 44 | 1166+44=1210; +24 pad=1234 ✓ |

Page bottom pad 36 → page height 1234+36=**1270**. Fold at y900 lands after the Costing
helper (884) — IDENTITY and all of CLASSIFICATION are above the fold; STOCKING and actions
scroll.

### Vertical stack inside the panel (all sums from y130)

Field block = label 12.5px/500 ink h18 + 6 + control; field gap 16; group gap 28; section
label (mono-caps §2, ink2) h14 + 12 below.

| Element | y | h |
|---|---|---|
| IDENTITY label · right-aligned "* required" 12px ink2 | 130–144 | 14 |
| 1 Item code* (text) | 156–220 | 64 |
| 2 Name* (text) | 236–300 | 64 |
| 3 Description (textarea 3 rows) | 316–424 | 108 (18+6+84) |
| CLASSIFICATION label | 452–466 | 14 |
| 4 Type* (select) | 478–542 | 64 |
| 5 Tracking mode (select) | 558–622 | 64 |
| 6 Category* (select) | 638–702 | 64 |
| 7 Base UoM* (select) | 718–782 | 64 |
| 8 Costing method (select) | 798–862 | 64 |
| — helper text 12px ink2 | 868–884 | 16 (+6 above) |
| STOCKING label | 912–926 | 14 |
| 9 Active (checkbox row) | 938–978 | 40 |
| 10 Reorder point (number, w 200) | 994–1058 | 64 |
| 11 Reorder quantity (number, w 200) | 1074–1138 | 64 |
| Actions: Create item · Cancel | 1166–1210 | 44 |

## 3. Per-region spec

- **Shell**: sidebar 248×900 per §3 verbatim — workspace switcher, section labels, nav rows
  (Inventory active: acc-t fill, acc text, 550), user card pinned bottom. No topbar (register
  shell; the crumb carries location).
- **Breadcrumb**: "Inventory / Items / New item" — 12px ink2, separators ink2, current
  segment ink/500. "Inventory" and "Items" are links.
- **h1**: "New item", 22px/650, −0.01em, lh 28, ink. No subtitle.
- **Card panel**: card fill, r14, 1px line border, shadow (§1 light shadow token), pad 24.
- **Section labels**: JetBrains Mono 10.5px/600, .06em, uppercase, ink2. On the IDENTITY row
  only, right-aligned "\* required" 12px ink2 (the 3.3.2 instruction, costs no height).
- **Text/number input**: h 40, r10, 1px line border, card fill, pad 0 12px, 13px/450 ink;
  placeholder 13px ink2. Number inputs w 200 (signals expected magnitude); all others w 512.
- **Textarea**: h 84 (3 rows lh20 + 11px vertical pad + border), r10, same border/fill,
  13px/450 ink, vertical resize only.
- **Select**: input geometry + 15px chevron (1.7px stroke, ink2) 12px from the right edge.
- **Checkbox** (register extension, ink-button idiom): 18×18, r5, 1px line border, card fill;
  checked = ink fill + white 12px check. Label "Active" 13px ink, gap 10; whole 40px row is
  the label/hit area, extended to 44px per §3 hit-target policy.
- **Create item**: standalone primary → 44px ink button outright (§3 policy), r10, pad 0 18px,
  13px/550 white on ink, **min-width 112** (holds "Creating…" without shift).
- **Cancel**: 44px chip button, r10, pad 0 16px, 1px line border, card fill, 13px ink; routes
  to the items list (03). Order: Create item left, Cancel right, gap 10, left-aligned.
- **Focus ring**: 2px solid acc, 2px offset, `:focus-visible` only (verified vs card, §3).

## 4. Content (exact labels and order from the live app — nothing renamed)

1. **Item code \*** — text; placeholder "e.g. ITM-BOLT-M6X20"
2. **Name \*** — text; placeholder "e.g. Hex bolt M6×20"
3. **Description** — textarea, empty
4. **Type \*** — select: Select… / Stocked / Non-stocked / Service
5. **Tracking mode** — select, default **None**; None / Lot / Serial
6. **Category \*** — select: Select… / "FG — FG" / "RM — RM" (the app's "code — name" format)
7. **Base UoM \*** — select: Select… / "EA — Each" / "HR — Hour"
8. **Costing method** — select, unset "—" (ink2); Moving average / FIFO. Helper below:
   "Leave unset to inherit the category's default."
9. **Active** — checkbox, checked by default
10. **Reorder point** — number, empty
11. **Reorder quantity** — number, empty

Submit **"Create item"**. Secondary **"Cancel"** → items list. Nothing else.

**Required-field policy (stated once, fixes the live bug):** all five required fields —
Item code, Name, Type, Category, Base UoM — carry the same three signals: visible "\*" after
the label (ink, `aria-hidden="true"`), `aria-required="true"` on the control, and "required"
in the accessible name via that attribute. The live app's select-only `required` is the bug;
this applies uniformly.

## 5. States owed

**(a) Validation error** — on failed submit:
- Error summary inserted at panel-inner top (y130, pushes the stack down): bad-bg fill, r10,
  pad 12px 14px; title 12.5px/600 bad-tx "5 fields need attention"; below it one link per
  failing field, 12.5px bad-tx **underlined**, each moves focus to its field. Container
  `role="alert"`, `tabindex="-1"`, focus moved to it on submit. bad-tx on bad-bg → 5.25 (§1).
- Per failing field: input border → 1px bad-tx (6.16 vs card clears the 3:1 non-text floor);
  message 12px/450 bad-tx, 6px under the control, e.g. "Item code is required." — linked via
  `aria-describedby`, `aria-invalid="true"` on the control.
- **No input is ever cleared.** Errors clear per-field on change. (The live app's raw
  "invalid UUID length 32" banner is replaced by these field-level messages.)

**(b) In-flight** — button label → "Creating…" (min-width 112 holds geometry, no shift),
`aria-disabled="true"` on the button; all controls `readonly`/`aria-disabled` — full-contrast
values stay visible (readonly, NOT the §1 disabled treatment: entered data must remain
readable). Polite live region announces "Creating item".

**(c) Unsaved-changes guard** — any dirty field: in-app navigation (Cancel, crumb, sidebar)
opens a confirm dialog "Discard new item?" — [Keep editing] (chip, default focus) /
[Discard] (ink button); browser close/reload gets native `beforeunload`.

**(d) Success routing** — Create → the new item's detail page (`/inventory/items/:code`),
focus to its h1, polite live region "Item ITM-BOLT-M6X20 created".

## 6. Type-table deltas from §2

| Role | Spec |
|---|---|
| Field label | Inter 12.5px/500, ink (new) |
| Field error | Inter 12px/450, bad-tx (new) |
| Helper text | Inter 12px/450, ink2 (= sub/meta) |
| Input value / placeholder | Inter 13px/450, ink / ink2 (= body) |

Everything else — h1, mono-caps, buttons, crumb — verbatim §2/§3.

## 7. Palette pairs used (§1 verified ratios only — none re-derived)

| Pair | Ratio |
|---|---|
| ink on card (labels, values, h1) | 17.74 |
| ink2 on card (helper, placeholder, section labels, crumb) | 5.15 |
| ink on bg (crumb current segment) | 16.57 |
| ink2 on bg (crumb links) | 4.81 |
| white on ink (Create item) | 17.74 |
| bad-tx on card (error text, error border ≥3:1 non-text) | 6.16 |
| bad-tx on bad-bg (error summary) | 5.25 |
| acc focus ring vs bg | 4.86 (floor 3.0) |
| line (input/panel borders) | decorative — never the sole state signal |

## 8. Accessibility

- One h1; SPA route in → focus h1 (`tabindex="-1"`). Skip link per §5.
- Native `<form>`; Enter submits; all controls native elements — no ARIA re-implementation.
- Required policy §4 above; error wiring §5(a): `role="alert"` summary + `aria-invalid` +
  `aria-describedby` per field; helper text also `aria-describedby` on Costing method.
- All targets ≥44px (inputs 40px visual + extended hit area per §3 policy; buttons 44 outright).
- Error state never signalled by border color alone — message text always accompanies it.
- Inherited register limitation (noted, not new here): card-fill + line-border input boundary
  is the register's own search-field idiom and rides below 3:1; boundary perception is carried
  by label-above, consistent 40px geometry, and the verified focus ring.
- Guard dialog (c): `role="alertdialog"`, focus-trapped, Esc = Keep editing.

## 9. Self-check

Sums re-added (564+560=1124 ✓; 130+1080+24=1234 panel bottom ✓; stack rows re-summed, all
gaps 16/28 consistent ✓); every token and ratio above read back against `_register.md` §1–§3
— no unlisted pair cited, no hue invented; labels and field order diffed against
`form-item.png` — exact match, nothing renamed.
