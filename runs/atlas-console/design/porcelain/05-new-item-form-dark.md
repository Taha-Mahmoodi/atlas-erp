# porcelain — 05 New item form — DARK

Canvas 1440×900 (page height 1270, scrolls). Composition anchor: **stacked-center**.
Background mode: **flat-surface**. Layout, region map, content, states and type identical to
`05-new-item-form-light.md` — this file records the dark pairs and every difference.

## Palette pairs used (§1 dark verified ratios only — none re-derived)

| Pair | Ratio |
|---|---|
| ink on card (labels, values, h1) | 14.68 |
| ink2 on card (helper, placeholder, section labels) | 6.23 |
| ink on bg (crumb current segment) | 15.91 |
| ink2 on bg (crumb links) | 6.74 |
| #17181c on ink fill (Create item — inverted ink button) | 15.33 |
| bad-tx on card (error text, error border ≥3:1 non-text) | 7.37 |
| bad-tx on bad-bg (error summary) | 6.65 |
| acc focus ring vs bg | 7.95 (floor 3.0) |
| line (input/panel borders) | decorative — 1.22 vs card, never the sole state signal |

## Differences from light

- **Substrates**: bg `#131418`, card `#1b1c22` (panel, inputs, chip button), line `#2a2c35`.
- **Shadow**: dark token — `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)` on
  the panel and the guard dialog.
- **Ink button** (Create item): fill = ink `#eeeef2`, text `#17181c` (§3 dark inversion).
  In-flight "Creating…" keeps the inverted pair.
- **Checkbox checked**: ink fill `#eeeef2`, check glyph `#17181c` (follows the button
  inversion; unchecked = card fill + line border as in light).
- **Error summary**: bad-bg `#361f1c`, bad-tx `#eb9486` — 6.65.
- **Per-field error**: border + message bad-tx `#eb9486` — 7.37 vs card.
- **Focus ring**: acc `#93a5ff` — 7.95 vs bg, 7.34 vs card.
- **Readonly in-flight values**: full-contrast ink, same as light — the §1 disabled
  treatment (ink2 @55%) is still never applied to entered data.
- No glass, no sparkline, no pills, no warn/ok tokens on this surface — nothing else varies.

## Self-check

Every hex and ratio above read back against `_register.md` §1 dark table — no unlisted pair
cited; layout math lives in the light file and was re-summed there.
