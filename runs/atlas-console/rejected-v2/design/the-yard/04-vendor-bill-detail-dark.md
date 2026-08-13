# the yard: Surface 4 of 7 — Vendor Bill Detail

**Coded-comp mode — DARK.** Canvas: 1440×900, same fixed desktop viewport. No image generated.

Layout is identical to the light spec — same design, one token set retuned, not a second art
direction (`DIRECTION.md` §6: "one design in two palettes"). **All boxes, gaps, column widths, row
heights, and arithmetic in `04-vendor-bill-detail-light.md` §1 hold unchanged here**: global top bar
`0,0→1440×56`, nav rail `0,56→240×844`, content well `272,88→1136×780`, breadcrumb `272,88→1136×24`,
title row `272,136→1136×44`, main card `272,204→760×440`, flow-strip card `1064,204→344×482`. This
file states only what changes under dark mode: the palette, the two card-shadow tokens, and the
status-token fills. §2–§9 below are delta notes against the light file, not a restatement of it.

## 1. Palette, paired, with ratios (dark)

Given (dispatch palette, restated for this surface, not recomputed):

| Pair | Values | Ratio |
|---|---|---|
| text-primary / substrate | `oklch(0.94 0.008 290)` / `oklch(0.19 0.012 290)` | ~14:1 |
| text-primary / card | `oklch(0.94 0.008 290)` / `oklch(0.24 0.012 290)` | ~13:1 |
| text-secondary / card | `oklch(0.68 0.015 290)` / `oklch(0.24 0.012 290)` | ~6:1 |
| accent-dark / substrate or card | `oklch(0.76 0.14 290)` | ~6:1 — breadcrumb links, Void button text |
| accent-tint-dark / accent-dark | `oklch(0.30 0.05 290)` / `oklch(0.76 0.14 290)` | ~5:1 — current-stage row highlight |
| hairline | `oklch(0.34 0.015 290)` | decorative-only, same caveat as light |

**New for this surface, computed (not given) — Approve fill, dark mode:** the dispatch's dark
palette has one accent role (`accent-dark`), not a separate ink/emphasis split. A filled button
needs a dark label on the light-ish `oklch(0.76 0.14 290)` fill, mirroring light mode's
white-on-fill logic inverted: label `oklch(0.16 0.02 290)` on fill `oklch(0.76 0.14 290)` —
**estimated ~9.5:1**, comfortably over the 16/600 floor light mode needed a flag for. Still set at
16px/600 for consistency across modes even though dark mode doesn't need the size crutch to pass.

Status-token pairs (given, restated):

| State | Fill / text | Used where on this screen |
|---|---|---|
| Closed | `oklch(0.5 0.01 290)` / white | PO row |
| Posted/Approved | `oklch(0.68 0.14 150)` / `oklch(0.16 0.02 150)` | GRN row, Bill row, title chip |
| Overdue/Error | `oklch(0.65 0.17 25)` / `oklch(0.16 0.02 25)` | modal destructive confirm only — note dark mode pairs this fill with **dark** text, not white, inverted from light |

Disabled Approve: fill `oklch(0.30 0.012 290)`, text `oklch(0.5 0.015 290)`, `aria-disabled="true"`
— exempt from the contrast floor, stated for completeness.

## 2. Surface tokens (dark)

- `radius-card: 16px` — unchanged, radius doesn't retune between modes.
- `shadow-card-dark: 0 1px 2px oklch(0 0 0 / 0.24), 0 6px 16px oklch(0 0 0 / 0.32)` — noticeably
  stronger alpha than light's `0.05 / 0.08`: on a dark substrate a soft shadow needs more density to
  read as elevation at all; card separation leans more on the `oklch(0.24)` vs `oklch(0.19)` card/
  substrate step than on the shadow alone.
- Avatar-chip fill: `oklch(0.30 0.012 290)` bg / `text-primary` initials (was accent-tint-on-
  accent-ink in light; dark mode keeps the chip neutral rather than tinted, so a row of chips
  doesn't compete with the accent-tinted current-stage row highlight next to it).

## 3. What doesn't change

Type table (§2 of the light file), the three line items and their sum (`24.00+18.00+12.00=54.00`),
the flow-strip's three rows and their accessible-name strings (§4 of the light file), the modal's
initial-focus-on-Cancel behavior (§5), the breadcrumb defect fix, and the content-direction line
(§6) — none of those are palette-dependent and are not restated here.

## 4. Self-check (embarrassment gate)

- Palette pairs re-read against §1: all six named pairs (text-primary×2, text-secondary, accent-
  dark, Closed, Posted/Approved) clear 4.5:1+; the two computed pairs (Approve fill, modal
  destructive confirm) are estimated and flagged, matching this run's own disclosure (`DIRECTION.md`
  §11 — no script-verified render yet).
- Layout numbers are the light file's, not re-derived here, and re-checked against that file before
  writing this line — no drift: same six boxes, same six sums.
- Terminology lock held (nothing in this file introduces new copy).
- Would I put my name on this: yes.

## 5. Could not fully satisfy

Same open item as the light file: the avatar-chip name/department wrap inside the 256px text column
is budgeted, not resolved to the character, in either mode.
