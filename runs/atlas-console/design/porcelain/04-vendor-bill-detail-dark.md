# 04 — Vendor bill detail · porcelain · DARK · 1440×900

Composition anchor: **right-rail-caption** · Background mode: **flat-surface**
Layout, regions, content, states, and type are identical to
`04-vendor-bill-detail-light.md` — all geometry math lives there. This file carries the
dark pairs and everything that differs.

## Palette — pairs used (§1 dark table, transcribed not re-derived)

| Pair | Ratio |
|---|---|
| ink #eeeef2 on bg #131418 | 15.91 |
| ink2 #9a9ca8 on bg | 6.74 |
| ink on card #1b1c22 | 14.68 |
| ink2 on card | 6.23 |
| acc #93a5ff on card (doc-flow current id, panel-head links) | 7.34 |
| acc on acc-t #232637 (active nav) | 6.46 |
| ink button (Post bill / Keep mine): fill #eeeef2, text #17181c | 15.33 |
| ok pill: #7fd6a4 on #1b2f24 | 8.15 |
| warn pill: #e4b566 on #332a17 | 7.48 |
| bad pill / EDIT CONFLICT label: #eb9486 on #361f1c / on card | 6.65 / 7.37 |
| focus ring acc vs bg | 7.95 (floor 3.0) |
| line #2a2c35 | decorative only — never sole boundary or state signal |

## Differences from light

- **Shadow** — dark token: `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)`
  on all three panels and the conflict/error panels.
- **Ink button** — inverts per §3: fill #eeeef2, text #17181c (Post bill, Keep mine).
- **Draft mute pill** — 1px dashed border in dark line #2a2c35, text ink2 #9a9ca8 on
  card → 6.23. Still no dot; label carries the state.
- **Skeleton** (state a) — blocks in dark line token #2a2c35 on card, r6; same geometry,
  same bounded lifetime; shimmer only when motion allowed.
- **Doc-flow gutter** — dots and vertical rule in dark line token; current dot and
  identifier in dark acc #93a5ff (7.34 on card). Rule remains decorative (1.22 vs card).
- **Disabled `Posting…`** — dark ink2 @55% on the inverted fill, contrast-exempt per §1
  note; border emphasis and pointer dropped as in light.
- **No glass, no sparkline, no chart on this surface** — nothing else in the dark
  register applies.

## Self-check

All ratios read back against `_register.md` §1 dark table verbatim; lowest text pair in
use is ink2 on card 6.23 ≥ 4.5 ✓; pills 8.15 / 7.48 / 6.65 all ≥ 4.5 ✓; focus 7.95 ≥ 3.0
✓. Layout sums verified in the light file §9; nothing geometric differs here.
Anchor/background from the §6 closed menus: right-rail-caption · flat-surface.
