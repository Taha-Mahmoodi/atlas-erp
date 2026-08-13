# porcelain — 07 Error state — dark — 1440×900

Anchor: **centered-statement** · Background: **flat-surface** (register §6 closed menus).
Layout, region map, content, all variants (a–c), the 422/404 collapse, the bounded-loading
rule, and the "what this replaces" record are identical to `07-error-state-light.md` —
only the pairs below differ. No glass, no shadow-bearing element on this surface (chip
buttons carry no shadow per §3).

## What differs

- **bg**: `#131418`. **Sidebar**: card `#1b1c22`, 1px line `#2a2c35` right border — §3
  shell dark, unchanged geometry; active Finance row acc-t `#232637` fill, acc `#93a5ff`
  text /550.
- **h1 / breadcrumb current segment**: ink `#eeeef2`. **Sentence, identifier echo,
  breadcrumb, retry note**: ink2 `#9a9ca8`.
- **Ink button** ("Back to vendor bills" / variant-b "Go to dashboard"): dark inversion
  per §1/§3 — fill `#eeeef2`, label 13px/550 `#17181c`.
- **Chip buttons** ("Go to dashboard", variant-a "Try again"): card `#1b1c22` fill, 1px
  `#2a2c35` border, 13px ink `#eeeef2`, r10 — geometry unchanged.
- **Focus ring**: 2px solid acc `#93a5ff`, 2px offset, `:focus-visible` only.
- **Still no bad-tx anywhere** — the light file's decision holds in dark: red reserved
  for data-loss-adjacent states, not for a calm not-found.

## Palette citation (pairs used only — §1 verified ratios, dark)

| Pair | Ratio |
|---|---|
| ink on bg (h1, breadcrumb current) | 15.91 |
| ink2 on bg (sentence, echo, breadcrumb, retry note) | 6.74 |
| #17181c on ink fill (ink button) | 15.33 |
| ink on card (chip labels, sidebar) | 14.68 |
| ink2 on card (sidebar rows) | 6.23 |
| acc on acc-t (active nav row) | 6.46 |
| acc focus ring vs bg | 7.95 (floor 3.0) |
| line vs card | 1.22 — decorative only, never sole signal |

## Self-check

Geometry inherited from the light file (all sums verified there, including variants a/b).
All dark hexes and ratios read back against `_register.md` §1 dark table; ink-button
inversion matches the §1 ink row note; anchor and background from §6's closed menus.
