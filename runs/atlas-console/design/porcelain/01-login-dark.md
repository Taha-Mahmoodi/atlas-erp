# porcelain — 01 Login — dark — 1440×900

Anchor: **centered-statement** · Background: **flat-surface** (register §6 closed menus).
Layout, region map, content, states, and type are identical to `01-login-light.md` —
only the pairs below differ. No glass, no sparkline, no sidebar on this surface.

## What differs

- **bg**: `#131418`. **Card**: `#1b1c22`, r14, 1px line `#2a2c35` border, dark shadow
  `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)`.
- **Masthead mark**: ink fill flips with the token — 26px r7 mark in ink `#eeeef2`, "A"
  12px/700 in `#17181c` (same treatment as the dark ink button, §1: **15.33**).
- **h1 / input values**: ink `#eeeef2`. **Subtitle, labels, placeholders**: ink2 `#9a9ca8`.
- **Inputs**: card fill `#1b1c22`, 1px `#2a2c35` border, r10 — unchanged geometry.
- **Sign in button**: dark ink button (§3) — fill `#eeeef2`, label 13px/550 `#17181c`.
  In-flight "Signing in…" state identical to light: label + `disabled`, fill held.
- **Error / validation text**: bad-tx `#eb9486` on card. Same copy, same geometry.
- **Focus ring**: acc `#93a5ff`, 2px solid, 2px offset, `:focus-visible` only.

## Palette citation (pairs used only — §1 verified ratios, dark)

| Pair | Ratio |
|---|---|
| ink on card | 14.68 |
| ink2 on card (labels, placeholder, subtitle) | 6.23 |
| #17181c on ink fill (button, mark "A") | 15.33 |
| bad-tx on card (error + validation) | 7.37 |
| acc focus ring vs bg | 7.95 (floor 3.0) |
| acc vs card (ring on inputs/button) | 7.34 (floor 3.0) |
| line vs card | 1.22 — decorative only, never sole signal |

## Self-check

Geometry inherited from the light file (sums verified there). All dark hexes and ratios
read back against `_register.md` §1 dark table; button/mark inversion matches the §1 ink
row note; menu tokens from §6's closed lists.
