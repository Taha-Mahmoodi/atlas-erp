# T5 — tinted status-pill system @ 40-row density · VERDICT

- **Run started:** Fri Aug 14 03:23:38 +0430 2026 · **finished:** Fri Aug 14 03:49:32 +0430 2026
- **Prototype:** `prototypes/status-pills.html` (standalone, no build step, `?theme=light|dark&state=default|compact|stress|gray[&bench=1]`)
- **Machine:** Apple M4, 16 GB, macOS 26.5.2, headless Chromium via gstack browse daemon, viewport 1440×900, dpr 1
- **Surface served:** 03 items list + every work list · **Tier:** 1 (CSS)

## Verdict: **SHIP**

Tier-1 flat per-row CSS; every owed check passed. Scroll fps is **PARTIAL** (no CPU
throttle reachable — see below); everything else is **TESTED**. The one design-relevant
discovery: the dispatch's compact-row arithmetic (36px) assumed single-line rows; the
register's two-line item cell renders 59px compact / 65px default. Floor (≥36px) passes
with margin — but DIRECTION.md's density policy should record the real numbers.

## Three-question answers (as dispatched, confirmed in pixels)

1. **Understand:** row state without reading — dot+label never color alone; Draft
   shape-distinct (dashed border, no dot); warn/bad rows pop preattentively while ok rows
   stay quiet. Confirmed in both themes and in the grayscale proof shots.
2. **Day shorter:** scanning forty rows for "what needs me" is the single most repeated
   read of the operator's day.
3. **Cost:** flat per-row CSS — 506 B raw / 280 B gzipped for the entire pill system.

## Measurements

### 1. Scroll fps — 200 rows (state=stress), rAF-driven ping-pong scroll, ~10 s — **PARTIAL**

| Theme | frames | mean fps | median fps | 1% low | worst frame | frames >20 ms |
|---|---|---|---|---|---|---|
| light | 778 | 77.7 | 90.9 | 38.2 | 26.8 ms | 77 |
| dark  | 795 | 79.4 | 92.6 | 38.0 | 29.1 ms | 73 |

Conditions: 1440×900, Apple M4, **unthrottled** — the gstack browse binary exposes no CPU
throttle and no CDP passthrough (`--help` checked), so **no throttled number exists; label
capped at PARTIAL for that reason.** Headless is not vsync-locked, hence >60 medians.
Method caveat: programmatic `scrollTo` inside rAF forces main-thread scroll + full repaint
each frame — an upper-bound-ish proxy; real user scroll composites cheaper. Worst frame
ever observed ≈29 ms. Supporting claim (stated, not measured): **low risk by
construction** — tier-1 CSS, zero production JS, no render loop, no filters/shadows per
row; the bench script is the only JS in the file and ships nowhere. Result painted in-page
(`#bench`) and captured in `shots/status-pills-stress-dark-bench.png`.

### 2. Geometry — **TESTED** (getBoundingClientRect, both themes identical)

| Check | default | compact | requirement |
|---|---|---|---|
| Row height | **65 px** (last row 64.5) | **59 px** (last 58.5) | compact ≥36 ✓ (margin +23) |
| Pill box height | **24 px** exact | **24 px** exact | =24 ✓ |
| Pill vertical centering (centre offset vs cell) | **0 px** | **0 px** | centered ✓ |
| ⋯ action centre-to-centre (consecutive rows) | **65 px** | **59 px** | ≥24 px (WCAG 2.5.8) ✓ |

**Flag for DIRECTION.md:** the dispatched "20px lh + 2×8px pad = 36px" assumed a
single-line row. The register's item cell is two lines (13px name + 11px mono id
sub-line, both on the inherited 20px line-height) → content ≈42 px. 42 + 2×8 + 1 border
= 59 compact; 42 + 2×11 + 1 = 65 default. Additionally ~2 px of the 42 is line-box growth
from the **fallback mono face** (Menlo/SF Mono metrics vs the 20px strut) — re-measure
row heights when JetBrains Mono Variable is vendored at handoff; expect ±2 px.

### 3. Byte cost — **TESTED**

| Asset | raw | gzip -9 |
|---|---|---|
| Pill CSS (complete system, all 4 variants + dot) | **506 B** | **280 B** |
| Whole prototype file (styles + 40-row data + bench script) | 10,478 B | 4,587 B |

No library. Nothing to vendor for this technique. Fonts: Inter Variable @font-face'd from
the repo's own `frontend/dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2` —
`document.fonts.check('13px "Inter Variable"')` → **true** (real face rendered, both
themes). **JetBrains Mono Variable is not in the repo**; mono roles (th caps, identifiers)
rendered on the register's fallback stack (ui-monospace/'SF Mono'/Menlo/Consolas), as the
register permits. Vendoring JBM is a handoff task, not this prototype's.

### 4. Contrast confirmations — script-computed WCAG 2.x (sRGB piecewise) — **TESTED**

Closes DIRECTION.md §3's queued items. Script: standard relative luminance, 3-dp output.

| Pair | fg | bg | computed | expected | Δ | verdict |
|---|---|---|---|---|---|---|
| ink on acc-t (light) | #17181c | #edf0fe | **15.624** | ≈15.7 | **0.08 — FLAGGED** | AA-pass |
| ink on acc-t (dark) | #eeeef2 | #232637 | 12.927 | ≈12.9 | 0.03 | AA-pass |
| acc on acc-t (light) | #3f5bf6 | #edf0fe | 4.580 | 4.58 | 0.00 | AA-pass (thin) |
| warn-tx′ on warn-bg (light) | #94650c | #fbf1de | 4.542 | 4.54 | 0.00 | AA-pass (thin) |
| ink2 on bg (light) | #6b6d76 | #f7f7f8 | 4.814 | 4.81 | 0.00 | AA-pass (thin) |
| pill ok light | #177a48 | #e7f6ed | 4.804 | 4.80 | 0.00 | AA-pass |
| pill warn light | #94650c | #fbf1de | 4.542 | 4.54 | 0.00 | AA-pass |
| pill bad light | #b23425 | #fbe9e7 | 5.251 | 5.25 | 0.00 | AA-pass |
| pill ok dark | #7fd6a4 | #1b2f24 | 8.154 | 8.15 | 0.00 | AA-pass |
| pill warn dark | #e4b566 | #332a17 | 7.478 | 7.48 | 0.00 | AA-pass |
| pill bad dark | #eb9486 | #361f1c | 6.653 | 6.65 | 0.00 | AA-pass |

The single >0.02 delta is the hand-computed "≈15.7": precise value is **15.62**. It was
recorded as an approximation, sits 3.5× above the 4.5 floor, and needs no palette change —
DIRECTION.md should carry 15.62. The three thin-margin pairs (4.58 / 4.54 / 4.81) are
confirmed at exactly the expected values; **no headroom exists on them — any future tint
tweak re-runs this script.**

### 5. Rendered-pixel check — sampled from 1440×900 dpr-1 screenshots — **TESTED**

| Sample | light rendered | light token | dark rendered | dark token |
|---|---|---|---|---|
| ok pill bg | #e7f6ed | =ok-bg ✓ | #1b2f24 | =ok-bg ✓ |
| ok dot | #177a48 | =ok-tx ✓ | #7fd6a4 | =ok-tx ✓ |
| warn pill bg | #fbf1de | =warn-bg ✓ | #332a17 | =warn-bg ✓ |
| warn dot | #94650c | =warn-tx′ ✓ (the corrected token) | #e4b566 | =warn-tx ✓ |
| bad pill bg | #fbe9e7 | =bad-bg ✓ | #361f1c | =bad-bg ✓ |
| bad dot | #b23425 | =bad-tx ✓ | #eb9486 | =bad-tx ✓ |
| mute (Draft) fill | #ffffff | =card ✓ (transparent) | #1b1c22 | =card ✓ |
| mute dashed border | #e9e9ee | =line ✓ | #282a34 | ≈line, antialiased¹ |

¹ Pill left edge sits at x=1055.34 (subpixel); the 1px dashed border blends with card.
Light theme sampled the same coordinate exactly on-token. Not a token mismatch.

## States built (all screenshotted at 1440×900 and viewed)

`shots/status-pills-<state>-<theme>.png`:

- `default-light` / `default-dark` — 40 rows, td pad 11px (+ `-fullpage` pair proving all
  40 rows / full pill distribution: 24 ok, 9 warn, 4 bad, 3 draft)
- `compact-light` / `compact-dark` — td pad 8px, rows 59 px, pills h24 centered
- `gray-light` / `gray-dark` — default table under `filter: grayscale(1)`: **state fully
  legible without color** — label text primary, dot marks live status, dashed-no-dot marks
  Draft; verified by eye on both shots
- `stress-dark-bench` — 200 rows with painted fps readout (light-theme bench numbers
  recorded in the table above; readout shot captured after the dark run)

**Motion:** pills are static — zero animation in the file, so there is no reduced-motion
delta by construction (stated, nothing to design).

**States NOT built, named:** the nine data states of the items-list surface (`empty`,
`loading`, `partial`, `error`, `denied`, `offline`, `stale`, `conflict`, `bulk`) are owed
by surface 03's comp and build, not by this technique prototype — dispatch scoped this
file to default/compact/stress/gray × two themes. Also not tested: narrow viewports (the
register is a fixed 1440×900 desktop console per §4; no narrow layout exists to test) and
`grid`-role keyboard semantics (build-time, register §5). Row data beyond the approved 9
items is structure-only stand-in (plausible names/quantities, no factual claims);
terminology lock held (item / vendor / warehouse).

## Evidence label summary

| Number | Label |
|---|---|
| Scroll fps (both themes) | **PARTIAL** — unthrottled only; no throttle mechanism reachable via browse binary |
| Row heights, pill height, centering, c2c spacing | **TESTED** |
| Byte costs | **TESTED** |
| Contrast table (11 pairs) | **TESTED** (script-computed) |
| Rendered pill pixels vs tokens | **TESTED** (screenshot-sampled, both themes) |
| "No jank on mid-range hardware" | **INFERRED** from tier-1 construction + unthrottled headroom — Gate B buys or re-tests |
