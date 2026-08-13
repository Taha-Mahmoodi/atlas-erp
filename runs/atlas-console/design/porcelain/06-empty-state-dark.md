# 06 · Empty state (items list, filtered-empty) — DARK

Canvas 1440×900 · porcelain · anchor: **centered-statement** · background: **flat-surface**
Layout, region map, content, data states (incl. the TRUE-EMPTY variant), copy, and
accessibility are identical to `06-empty-state-light.md` — this file records the dark
palette pairs and everything that differs.

## Palette pairs used (§1 dark, verified — cited, not re-derived)

| Pair | Ratio |
|---|---|
| ink `#eeeef2` on card `#1b1c22` (statement line 1, thead context) | 14.68 |
| ink2 `#9a9ca8` on card (statement line 2, th, placeholder) | 6.23 |
| ink on bg `#131418` (crumb current, h1) | 15.91 |
| ink2 on bg (crumb, pagehead sub, count line) | 6.74 |
| acc `#93a5ff` on bg ("+ Add filter", focus ring vs bg) | 7.95 |
| acc on acc-t `#232637` (filter chips, active nav) | 6.46 |
| ink-button dark: ink fill `#eeeef2`, text `#17181c` | 15.33 |
| line `#2a2c35` | decorative only (1.22 vs card) — never the sole boundary |

## Differences from light

- **Ink buttons invert** (§3): "New item" (page head) and the 44px "Clear filters" CTA —
  and the true-empty "New item" CTA — render ink fill `#eeeef2` with `#17181c` text
  (15.33). Geometry unchanged: CTA 44px outright, pad 0 16px, r10, 13px/550.
- **Shadow** (panel, ink buttons per §3): `0 1px 2px rgba(0,0,0,.3),
  0 10px 28px -8px rgba(0,0,0,.4)`.
- **Filter chips**: acc-t `#232637` fill, acc `#93a5ff` text (6.46). Dismiss ✕ inherits
  acc.
- **Focus ring**: 2px solid acc `#93a5ff`, 2px offset, `:focus-visible` only — 7.95 vs bg,
  7.34 vs card (§1 verified).
- No glass, no sparkline, no pills, no status colors on this surface in either mode —
  nothing else to re-pair. Live-region behavior, focus routing, and chip semantics carry
  over unchanged.

## Self-check

All dark hexes and ratios read back against `_register.md` §1 dark table — no re-derived
values; button inversion and shadow read back against §3; anchor + background tokens
confirmed against the §6 closed menus (same tokens as light — same surface, same state).
