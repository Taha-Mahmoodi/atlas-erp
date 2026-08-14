# T3 — monochrome paired-bar cash-flow chart · VERDICT

- **Run start:** Fri Aug 14 03:22:55 +0430 2026
- **Run end:** Fri Aug 14 03:30:10 +0430 2026
- **Prototype:** `prototypes/bar-chart.html` (one standalone file, no build step)
- **Surface:** 02 role home · **Tier:** 1 (DOM/CSS, zero JS in the chart, zero libraries)
- **Machine:** M-series MacBook (darwin 25.5.0), gstack browse headless Chromium, viewport 1440×900, DPR 1

## Verdict: **ship** — evidence label **TESTED**

Tier-1 DOM/CSS chart, static (no render loop, no animation → no reduced-motion delta
exists and no frame-rate cost exists; performance is low-risk **by construction** — that is
a stated claim, the only INFERRED item here; everything below is measured). All five
dispatched states built and rendered in both themes; every screenshot viewed. Rendered
pixels match tokens exactly. Baseline lands on whole pixels. Byte cost far inside tier 1.

**Recommendation: ship the `bar-lo` variant (accessible-gray), not the as-approved 1.21:1
gray.** Reason: the gray bar is one of the two data series — it carries meaning, so the
WCAG 1.4.11 ≥3:1 non-text floor applies, and the approved `line` token measures **1.21:1
light / 1.22:1 dark** (script-computed, confirmed in rendered pixels). In the light
screenshot the gray series visibly almost vanishes. `bar-lo` stays a neutral porcelain
gray (same cool cast, hue 275, chroma 0.007 — the line token's chroma family), keeps ink
dominant, introduces no hue, and reads as the same register. The human decides at Gate B;
`state=normal` was left exactly as approved and both variants are screenshotted.

## Three-question answers (from dispatch, confirmed)

1. **Understand:** in/out cash by month on a shared baseline — position + length encoding
   (Cleveland & McGill's two most accurate channels); monochrome keeps the accent meaning
   "interactive," never "data."
2. **Day shorter:** "are we above last month?" answered on the home screen without opening
   Reports.
3. **Cost:** measured below (~3.5KB chart, whole file 7.6KB raw / 2.3KB gzip). The 1.21:1
   contrast risk named in the dispatch is confirmed real; the fix variant is built.

## Value→height mapping (real, not hand-tuned) — TESTED

Whole-dollar values as CSS custom properties; chart scale max on the container:

- `.bars { --max: 250000 }` (chart scale maximum, dollars)
- each bar: `style="--v: <dollars>"`
- `height: round(nearest, calc(var(--v) / var(--max) * 180px), 1px)`
  (plain `calc()` fallback declared first for engines without CSS `round()`;
  `CSS.supports('height','round(nearest,10.5px,1px)')` → **true** in test Chromium)
- bar 1 (gray) = cash out · bar 2 (ink) = cash in

Normal-state data (dollars → measured rendered px, all exact):
Mar 104,600→75 / 150,200→108 · Apr 87,900→63 / 119,400→86 · May 137,200→99 / 183,100→132 ·
Jun 120,300→87 / 129,800→93 · Jul 154,900→112 / 219,600→158 · Aug 124,700→90 / 175,300→126.
Echoes the approved frame's silhouette within 1px at every bar. **Stand-in data:** all
dollar values are invented placeholder seed data (as the approved frame's are); no
provenance claim.

## Whole-pixel baseline check — TESTED

- As built (phead line-height pinned 16px): every bar bottom at **y = 269.00** exactly;
  every bar height a whole px (`round()` guarantee).
- As-approved rendering (lh `normal`, toggled live and re-measured): phead 15.0px, bottom
  **268.00** — also whole with Inter Variable in Chromium. The 16px pin is deterministic
  insurance for fallback stacks and is the **only deviation** from the approved frame
  (+1px phead height, visually nil); revert if Gate B prefers byte-exact conformance.

## WCAG ratios — TESTED (script-computed, `scratchpad/wcag.py`; register §1 cross-check passed: ink2 5.15/6.23 reproduced)

| Pair | Light | Dark |
|---|---|---|
| line-token gray bar vs card | **1.21:1** ✗ (floor 3.0) | **1.22:1** ✗ |
| ink bar vs card | 17.74:1 ✓ | 14.68:1 ✓ |
| axis label ink2 vs card | 5.15:1 ✓ (text floor 4.5) | 6.23:1 ✓ |
| **proposed bar-lo vs card** | **#939599 → 3.0002:1** ✓ | **#66676b → 3.0081:1** ✓ |

`bar-lo` derivation: OKLCH walk at hue 275, chroma 0.007, 0.001-L steps, contrast checked
on the quantized hex. Light = lightest value clearing 3.0 vs `#ffffff`:
`#939599` = oklch(66.9% 0.007 275). Dark = darkest value clearing 3.0 vs `#1b1c22`:
`#66676b` = oklch(51.3% 0.007 275). Boundary-verified: one 0.002-L step past either
fails (2.99 / 2.96). **Headroom note:** light sits at 3.0002; `#939499` (one step darker,
visually identical) measures 3.0274 if Gate B wants margin against other color pipelines.

## Rendered-pixel confirmation — TESTED (PIL sampling of the 1440×900 PNGs)

| Shot | Gray bar | Ink bar | Card |
|---|---|---|---|
| normal-light | `#e9e9ee` ✓ | `#17181c` ✓ | `#ffffff` ✓ |
| normal-dark | `#2a2c35` ✓ | `#eeeef2` ✓ | `#1b1c22` ✓ |
| accessible-gray-light | `#939599` ✓ | `#17181c` ✓ | `#ffffff` ✓ |
| accessible-gray-dark | `#66676b` ✓ | `#eeeef2` ✓ | `#1b1c22` ✓ |

Every sampled pixel matches its token exactly (sampled mid-bar at CSS 80,240 / 120,240;
card at 500,100).

## Density numbers @ 602px panel (566px inner, bars pad 0 6px → 554px row) — TESTED

| State | Group width | Bar width | Gaps | Note |
|---|---|---|---|---|
| normal (6 mo) | 80.33px | 38.17px | 14 between / 4 within (held) | as approved |
| dense (12 mo) | 33.16px | **14.58px** | **14 / 4 — gaps hold, bars compress** | pairing legible, 3-letter labels fit (33.16px each, no collision), baseline still 269.00 |
| sparse (2 mo) | 269px | **132.5px** | 14 / 4 | **fails visually as-approved** — slabs, radius lost in mass |

**Sparse finding (not silently applied):** if <4 months is a real case, cap
`.bargrp { max-width: 80px }` and the sparse chart holds the 6-month bar width. One line;
Gate B / build decision.

## Byte cost — TESTED (`wc -c`, `gzip -9`)

- Whole file: **7,603 B raw / 2,336 B gzip** (includes all 5 states, both themes, comments, harness)
- Chart CSS (marked block): **2,199 B** · chart DOM (normal panel): **1,366 B** → chart ≈ **3.5KB raw** uncommented-unminified; comfortably tier 1. Dispatch's ~1KB estimate was optimistic but the tier holds with a wide margin. Zero libraries, zero chart JS (3-line query-string harness only, excluded from chart cost).

## States built (× light + dark, 10 screenshots, all viewed)

`shots/bar-chart-{normal,dense,sparse,empty,accessible-gray}-{light,dark}.png` @ 1440×900.

**Not built (named):** the remaining tool-shaped data states — loading, partial, error,
denied, offline, stale, conflict, bulk — are owed by surface 02 as a whole, not dispatched
to this component prototype (dispatch enumerated the five above; the register's skeleton
spec §3 covers the chart's loading geometry). Chart is static: no motion → no
reduced-motion variant exists to build; `full/reduced/nogpu` render states do not apply
(no GPU path, no animation). No throttled frame-rate number exists because there is no
render loop — nothing to measure; this is the "low risk by construction" claim, INFERRED,
and the only unmeasured claim in this file.

## Fonts

Inter Variable (latin subset) loaded via `file://` @font-face from
`frontend/dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2` — confirmed loaded
(`document.fonts.check` true). JetBrains Mono Variable is **not yet in the repo**; the
mono-caps head rendered the register's fallback stack (`ui-monospace` → SF Mono on this
machine). Vendoring JetBrains Mono is a §7 handoff task, not mine.

## Accessibility notes

- Chart carries `role="img"` + aria-label naming series and range (gray = out, ink = in).
- Series are distinguished by lightness, not hue — but a name legend exists only in the
  aria-label; a visible in/out legend is a Loop 3 copy/design decision (the approved frame
  has none). Flagged, not added.
- Empty state keeps the Weekly/Monthly/Yearly meta over no data — Loop 3 copy decision.
- Design-hook findings (Inter "overused", flat type scale) are false positives: face and
  sizes are the Gate-A-locked register values in a reference-conformance run; unchanged,
  no suppression recorded.
