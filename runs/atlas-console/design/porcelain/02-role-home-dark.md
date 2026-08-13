# porcelain · 02 Role home — dark · 1440×900

Composition anchor: **left-rail-caption** · Background mode: **flat-surface**
(floating glass palette does not change background mode — _register.md §6.)
Layout, region math, content, data states, type, and a11y: **identical to `02-role-home-light.md`** (§1–§4, §6 there). This file records the dark pairs and every difference. MATCHES the approved dark frame (`gate-a-approved-porcelain.html` 364–430).

## 1. Dark palette pairs used (§1 verified — never re-derived)

| Use on this surface | Pair | Ratio |
|---|---|---|
| Body text | ink `#eeeef2` on bg `#131418` | **15.91** |
| Card text (values, identifiers, palette rows) | ink on card `#1b1c22` | **14.68** |
| Secondary on bg / card | ink2 `#9a9ca8` | **6.74** / **6.23** |
| Sparkline + "View all" + active-nav icon color | acc `#93a5ff` on card | **7.34** (graphical floor 3.0 ✓) |
| Active nav text | acc on acc-t `#232637` | **6.46** |
| Focus ring vs bg | acc | **7.95** (floor 3.0) |
| Ink button (INVERTED: fill `#eeeef2`, text `#17181c`) | | **15.33** |
| Pill ok | `#7fd6a4` on `#1b2f24` | **8.15** |
| Pill warn | `#e4b566` on `#332a17` | **7.48** |
| Pill bad | `#eb9486` on `#361f1c` | **6.65** |
| ↑ delta on card | ok-tx on card | **9.76** |
| ↓ delta on card | bad-tx on card | **7.37** |
| Glass composite (62% card over bg = `#18191e`) | ink on it | **15.17** (computed) |
| line `#2a2c35` | decorative only | 1.22 vs card — never sole signal |

## 2. Differences from light

- **Shadow token**: `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)` on stat cards and panels — reads as depth, not tint; hairline border still present (shadow never the sole boundary).
- **Ink button** ("Export CSV"): fill flips to ink `#eeeef2`, label `#17181c` (15.33). Workspace-switcher 26px mark flips identically (ink fill, dark "A").
- **Bar chart** stays monochrome with the same two tokens re-resolved: gray bar = line `#2a2c35`, dominant bar = ink `#eeeef2` (dark's btn-ink). Accent still never a data color. Same heights, radii, gaps as light §2.
- **Sparkline**: acc `#93a5ff`, stroke 1.8px, vs card **7.34** (light was 5.20) — cited, not re-derived.
- **Glass palette material**: same 62% card + blur(18px) saturate(150%), r16; **border becomes 1px `color-mix(in srgb, #ffffff 14%, transparent)`** (light rim, since a white-mixed border would glow wrong at 40%); shadow follows the dark shadow depths (`0 24px 60px -12px` black-weighted). Highlighted row = 85% card composite; kbd chips card fill + line border as in light, ink2 text at 6.23.
- **Focus ring**: same 2px acc / 2px offset geometry; ratio improves to 7.95 vs bg.
- **Mute pill (Draft)**: dashed `#2a2c35` border + ink2 text — 6.23 on card carries it; border remains decorative reinforcement, text is the signal.
- **Skeletons** (state a): blocks use dark line token `#2a2c35` on card, r6, same geometry as light §3a; shimmer highlight stays subtle (line → ~4% white mix), motion-gated, static under reduced motion.
- **Reduced-motion palette**: instant, fully opaque **card `#1b1c22`** panel, same border/shadow/rows — a designed state, not a fallback.
- Empty state (b) and palette-closed default (c): unchanged from light apart from token resolution.

## 3. Self-check
Region sums inherited from light §7 (re-added there: 1440/1120/268×4/602+502 all ✓). Every hex above read back against _register.md §1 dark table ✓ · ink-button inversion and glass border delta match the approved `.po.dark` block ✓ · anchor/background tokens from the §6 closed menus ✓.
