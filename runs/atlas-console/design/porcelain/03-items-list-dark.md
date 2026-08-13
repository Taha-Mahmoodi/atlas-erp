# porcelain — 03 Items list — DARK

Canvas 1440×900. Composition anchor: **dense-grid**. Background mode: **flat-surface**.
HUMAN-APPROVED reference execution (gate-a-approved-porcelain.html lines 487–537, `.po.dark`).
Layout, column arithmetic, row anatomy, content, states, keyboard contract, and type are
**identical to `03-items-list-light.md`** §1–§6 and §8 — this file specs the dark pairs and
every rendering difference. Tokens/ratios from `_register.md` §1 dark table (never re-derived).

## Dark palette pairs used (§1 verified ratios)

| Pair | Ratio |
|---|---|
| ink #eeeef2 on bg #131418 (h1, crumb current) | 15.91 |
| ink2 #9a9ca8 on bg (crumb, sub, pagination) | 6.74 |
| ink on card #1b1c22 (table cells, chrome) | 14.68 |
| ink2 on card (th, identifiers, Reorder col, placeholder, Draft pill text) | 6.23 |
| ink-btn dark: fill #eeeef2, text #17181c (New item button, checked checkbox) | 15.33 |
| acc #93a5ff on acc-t #232637 (filter chips, selection bar, active nav) | 6.46 |
| acc on bg (+ Add filter, focus ring — ring floor 3.0) | 7.95 |
| acc vs card, non-text (sort indicator, checked fill — floor 3.0) | 7.34 |
| ok-tx #7fd6a4 on ok-bg #1b2f24 (In stock) | 8.15 |
| warn-tx #e4b566 on warn-bg #332a17 (Low stock) | 7.48 |
| bad-tx #eb9486 on bad-bg #361f1c (Out of stock) | 6.65 |
| line #2a2c35 | decorative only — 1.22 vs card, never the sole signal |

## Everything that differs from light

- **Ink button inverts** (§1): "New item" = fill #eeeef2, text #17181c /550 → 15.33. Same
  38px visual / 44px hit.
- **Checkbox**: unchecked 1.5px ink2 border (6.23 vs card, clears 3:1 non-text); checked =
  ink fill #eeeef2 + #17181c check — the ink-button pair, 15.33. Same geometry.
- **Shadow token**: `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)` on the
  table panel (only shadowed element on this surface).
- **Skeleton blocks**: line token #2a2c35 on card, same r6 geometry as light §5a; shimmer
  only when motion allowed, static otherwise.
- **Hover row**: `color-mix(in srgb, acc-t 45%, card)` with dark values → a near-card navy
  lift. **Selected row**: full acc-t #232637, text stays ink (pair untabulated in §1 —
  same flag as light §9; ink L 95% on L 27.4% surface, comfortably above floor, unverified).
- **Selection action bar**: acc-t fill, "1 selected" + Change status · Export · ✕ in acc
  → 6.46. Same in-flow geometry (panel 512→566).
- **Focus ring**: 2px solid acc #93a5ff, 2px offset — 7.95 vs bg, verified per §3 vs card
  and acc-t.
- **Sort indicator**: acc #93a5ff active (7.34 vs card non-text), ink2 on hover/focus.
- **Disabled Prev**: ink2 at 55% opacity, contrast-exempt, never the only disabled signal.
- **Mute/Draft pill**: transparent fill, 1px dashed line #2a2c35 border, ink2 text (6.23),
  no dot — dashed border + label carry the state, not the low-contrast hairline alone.
- **No glass, no gradient anywhere on this surface** — flat-surface holds; the ⌘K chip in
  the searchfield is a kbd chip (card fill, line border, `0 1px 0 line`), not the palette.

## Self-check

Layout math inherited from light §1/§3 (1090 column sum, 512 panel, 900 vertical) — not
re-derived here. Dark tokens read back against §1 dark table: acc is #93a5ff (not light's
#3f5bf6), warn pair #332a17/#e4b566, shadows are the dark token, btn-ink inverted. Flags
carried from light §9: ink-on-acc-t unverified pair; approved-frame filter/data mismatch
kept verbatim; density toggle is the sole extension beyond the approved frame.
