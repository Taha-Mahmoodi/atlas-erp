# T2 — inline SVG sparklines in stat cards · VERDICT

Run started: Fri Aug 14 03:22:29 +0430 2026
Run ended:   Fri Aug 14 03:48:39 +0430 2026
Machine: Apple M4, macOS 26.5.2. Viewport: 1440×900, devicePixelRatio 1 (gstack browse daemon, headless).
Surface served: 02 role home. Tier: 1 (SVG native, zero JS, zero render loop).

## Verdict: **ship** — evidence label **TESTED** (with one PARTIAL sub-claim, DPR-2, noted below)

The technique holds. Rendered stroke is the exact §1 accent in both themes (RGB distance 0.0),
layout is pixel-stable across normal/empty (0px delta on every rect dimension), degenerate
series render sanely, cost is 209 B per sparkline with no JS and no main thread. Tier-1 by
construction: static SVG, no render loop — the "low risk by construction" performance claim,
stated, not measured, per the loop's rule for tier-1 CSS/SVG.

## Three-question answers (from dispatch, carried)

1. **Understand:** the number says level, the sparkline says direction — "is this normal?" at a glance.
2. **Day shorter:** saves the Reports navigation for the two stats checked every morning.
3. **Cost:** ~300 B est. → **209 B measured** per sparkline, zero JS, zero main-thread.

## Decision of record: `vector-effect="non-scaling-stroke"` — YES, required

76×22 display over an 80×24 viewBox is a **non-uniform** scale (0.95 x, 0.9167 y). Without
the attribute the spec'd 1.8px stroke renders at ~1.68px effective and slightly elliptical in
cross-section. With it, the stroke is pinned at exactly 1.8 CSS px. Clipping was checked:
points padded to x∈[1,79], y∈[2,22] in user units leaves ≥0.05px clearance for the 0.9px
half-stroke plus round caps inside the 76×22 box. **TESTED** — measured stroke thickness
median 2 device px at DPR 1 (correct raster of 1.8px), no clipping visible in any screenshot.

## Measurements

### 1. Rendered stroke color (TESTED — M4, 1440×900, DPR 1, PNG pixel sampling via PIL 11.3.0)

| Theme | Expected (§1) | Nearest rendered pixel | RGB distance | Stroke thickness (device px) |
|---|---|---|---|---|
| light | `#3f5bf6` | rgb(63, 91, 246) | **0.0** | median 2, min 1, max 2 |
| dark | `#93a5ff` | rgb(147, 165, 255) | **0.0** | median 2, min 1, max 2 |

Exact accent renders at stroke core in both themes; antialias skirt within tolerance
(threshold ΔRGB < 100 Euclidean; 124/116 accent-ish px over the 76×22 region). The §1
script-verified ratios (5.20 light / 7.34 dark vs 3.0 floor) therefore apply to the rendered
pixels — confirmed, not re-derived.

### 2. Stroke crispness DPR 1 vs DPR 2 (DPR 1 TESTED · DPR 2 **PARTIAL/INFERRED**)

- DPR 1: TESTED as above — clean 2px raster, uniform along the whole polyline (flat-line
  case: min=max=2, zero wobble).
- DPR 2: **the browse CLI exposes no device-pixel-ratio option** (`--help` verified: only
  `viewport <WxH>`), and the daemon reports devicePixelRatio 1. No DPR-2 raster was produced,
  so the DPR-2 claim is capped at **PARTIAL**, reason: no instrument. The residual claim is
  **INFERRED**: SVG rasterizes at device resolution by construction; non-scaling-stroke 1.8px
  → 3.6 device px at DPR 2. No mechanism for DPR-2-specific failure exists in a static SVG,
  but it was not measured.

### 3. Byte cost (TESTED)

| Item | Bytes |
|---|---|
| One sparkline SVG element (12-point series, incl. vector-effect attr) | **209 B** |
| Whole prototype file (8 states × structure, tokens, harness) | 8,666 B raw · 2,544 B gzip −9 |
| JS shipped by the technique | **0 B** (prototype harness has 4 lines for query-string state switching only; the sparklines are static markup) |

### 4. Layout stability, normal vs empty (TESTED — browse `getBoundingClientRect`)

| State | Label-row rect (x, y, w, h) |
|---|---|
| normal (sparkline present) | 179, 53, 230, 22 |
| empty (sparkline absent) | 179, 53, 230, 22 |

**Delta: 0px on every dimension.** Mechanism: `.labrow { min-height: 22px }` pins the row to
the sparkline's height whether or not the SVG is present.

Bonus stability fix found and TESTED during the run: the loading skeleton card initially
measured 108px vs the loaded card's 114px (block-margin collapsing between skeleton blocks —
labrow 8px mb swallowing sk-val 3px mt, sk-val 3px mb collapsing into sk-delta 4px mt).
Fixed with `#loading .card { display: flex; flex-direction: column }` (flex children don't
collapse margins) plus sk-delta margins 4/2 filling the loaded delta's 16px line box + 2px
margin. Re-measured: loading card **114px = loaded card 114px**, zero reflow on load.

## States built (all 8 screenshotted at 1440×900, DPR 1, and visually reviewed)

- `?state=normal` × light/dark — approved data: Total revenue $128,400 ↑2.6% (sparkline),
  Open orders 132 ↑8 (sparkline), Low-stock 6 of 214, AP due $23,900.
- `?state=empty` × light/dark — revenue series has no data, sparkline absent entirely,
  row height held (measured, above).
- `?state=degenerate` × light/dark — 2-point series renders as a clean single segment;
  flat series (all values identical) renders centered: stroke occupies rows 63–64 of
  rect y 53–75 (center 64) — **on the vertical center, not an edge** (TESTED, pixel scan).
- `?state=loading` × light/dark — static skeleton, line-token blocks r6, geometry-matched
  (114px = 114px). Shimmer intentionally out of scope: the skeleton technique is proven
  separately per dispatch.

**States not built, named:** none from the dispatch list. Reduced-motion is **identical by
construction** — the sparklines are static markup, nothing animates above the fold, so a
duplicate reduced state would prove nothing; stated here per dispatch instead of built.
No 390px-wide shots: surface 02 is a desktop console at the register's fixed 1440×900 canvas
(§4 layout constants); dispatch specified 1440×900 only.

## Screenshots (all at /Users/taha/Documents/atlas-erp/runs/atlas-console/prototypes/shots/)

- sparklines-normal-light.png · sparklines-normal-dark.png
- sparklines-empty-light.png · sparklines-empty-dark.png
- sparklines-degenerate-light.png · sparklines-degenerate-dark.png
- sparklines-loading-light.png · sparklines-loading-dark.png

## Fonts (dispatch side-notes)

- **Inter Variable rendered from the repo's built asset** via file:// `@font-face`
  (`frontend/dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2`):
  `document.fonts.check('650 26px "Inter Var"')` → **true** (TESTED). Values/deltas in the
  screenshots are real Inter at real weights.
- **JetBrains Mono: no woff2 exists anywhere under frontend** (find verified) — mono-caps
  labels rendered in the fallback stack (ui-monospace → SF Mono on this machine). Caveat for
  the builder, not for this verdict: label glyph metrics will shift slightly when JetBrains
  Mono Variable is added per §2, but the labrow min-height pins row geometry regardless.

## Budget ledger side-task: woff2 on disk under frontend

TESTED (on-disk `ls -l`, deduplicated — dist/assets files are byte-identical copies of the
fontsource files):
- Inter latin wght normal (the load-bearing one): **48,256 B**
- Inter latin-ext wght normal: 85,068 B · greek 18,996 B · greek-ext 11,232 B ·
  cyrillic 18,748 B · cyrillic-ext 25,960 B · vietnamese 10,252 B
  (dist ships these 7 subsets; browsers fetch per unicode-range, latin only for this UI)
- node_modules @fontsource-variable/inter: full matrix (wght/opsz/standard × normal/italic),
  10,252–146,460 B per file — build inputs, not shipped weight.
- **JetBrains Mono: 0 files found.** Adding it per §2 (Latin + tabular digits subset) is
  estimated **~35–45 KB** woff2 — **INFERRED** (typical fontsource variable latin subset
  size; no file exists to measure).

## Integrity notes

- All numbers ($128,400, 132, 6/214, $23,900) are the dispatch-approved seed data, not
  invented facts. Sparkline series are stand-in shapes for trend rendering only.
- No CDN dependency, nothing to vendor: the technique is inline markup.
- Sparklines are `aria-hidden="true"`: direction is duplicated in the delta text
  (↑ 2.6% / ↑ 8), so no information is lost to screen readers; §1's "never color alone"
  holds because the delta arrow + text carries the signal.
- Browse lock protocol honored: lock acquired/released around every daemon use; one long
  wait (~16 min total) while the status-pills worker held the lock; no steal was needed
  (lock never exceeded 10 min stale), daemon never killed.

## Caveats for the builder (none gate the ship)

1. Keep `vector-effect="non-scaling-stroke"` and the x∈[1,79] / y∈[2,22] data padding
   together — dropping either thins or clips the stroke.
2. Keep `.labrow { min-height: 22px }` — it is the entire no-reflow guarantee.
3. Skeleton cards must not rely on collapsed block margins — flex column, per the 114px fix.
4. Flat/degenerate series need the normalizer to map "no range" to viewBox y=12, not y=0.
