# T4 — skeleton loading states · VERDICT

**Run start:** Fri Aug 14 03:23:13 +0430 2026
**Run end:** Fri Aug 14 03:48:13 +0430 2026
**Machine:** Apple M4, macOS 26.5.2 · chrome-headless-shell 1208 (Playwright chromium, gstack browse daemon + one independent playwright-core 1.58.2 instance for CDP throttling)
**Viewport:** 1440×900 for every number below (screenshots are full-page captures at 1440 width)
**Prototype:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/prototypes/skeleton.html` (standalone, no build step; states via `?theme=light|dark&state=skeleton|loaded|swap|reduced`, stress via `&rows=N&fps=1`)

## Verdict: **SHIP** — evidence label **TESTED** (one sub-claim PARTIAL, named below)

Tier 1, CSS only, zero library bytes. Every number below was measured on this machine at this
viewport; the two headline claims — zero CLS on swap and compositor-only shimmer — are
measured, not adjectives.

## Three-question answers (from dispatch, confirmed by the prototype)

1. **Understand:** what is coming and where; layout never shifts, so the operator's eyes stay
   parked on the row they were reading. *(Measured: swap CLS = 0, geometry Δ = 0.)*
2. **Day shorter:** zero relearning per load; no click ever lands where a button was.
   *(Measured: every skeleton cell/box occupies the identical rect as its loaded counterpart.)*
3. **Cost:** 1,064 B of CSS (646 B gzipped). The claims are numbers: CLS 0.00000, fps
   invariant under 4× CPU throttle.

## Measurements

### 1. CLS of the swap — **TESTED** · claim: 0 · measured: **0**

`PerformanceObserver('layout-shift', buffered)`; boot bucket frozen at t=1400 ms, swap fires
at t=1500 ms (120 ms opacity crossfade, `cubic-bezier(0.2,0,0,1)`, both layers stacked in one
grid cell — no property that can move layout is touched), read at t=3000 ms.

| Run | swap-window CLS | boot CLS (pre-swap) |
|---|---|---|
| light, daemon, unthrottled | **0** | 0 |
| dark, daemon, unthrottled | **0** | 0 |
| light, CDP 4× CPU throttle | **0** | 0.02302 |

Boot CLS 0.02302, when it appears, is the *prototype's* font arrival (embedded woff2 finishing
after first layout re-metrics the text; race-dependent, seen in 2 of ~8 loads). It is not a
property of the technique: production loads Inter app-shell-wide, not per-route. Loop 3 should
still preload the woff2 (`<link rel="preload" as="font">`) — noted as a freebie.

### 2. Geometry match — **TESTED** · target ±2px positions, exact row/card heights · measured: **0.00 px, all 49 pairs**

In-page `getBoundingClientRect` comparison of every tagged skeleton element against its loaded
counterpart (49 pairs: 4 stat cards + their label-row/value/delta/spark line boxes; table panel,
all 8 rows, all 8 cells of row 1, pagination line; meta card, all 6 dt + 6 dd). Max Δtop = 0,
Δleft/Δright (per alignment) = 0, container Δheight = 0, Δwidth = 0 — every region, both themes.
Method note: pairs compare **line boxes / cells / containers** (the things that determine where
clicks land); the gray blocks are centered inside line boxes whose heights equal the real
elements' line heights, so the match is by construction and the instrument verifies it.

Instrument earned its keep — three real bugs found and fixed before any state was screenshot:
1. Stat-card `<small>of 214</small>` under flex `align-items:baseline` inflated the real value
   row 32→37 px (approved-frame CSS carries this latently). Fix: `line-height:1` on `small`.
2. dl STATUS field: inline pill in a `line-height:20` dd produced a 25.5 px line box (inline
   baseline overhang), cascading +1.5 px onto fields 3–6. Fix: dd becomes flex, height 24.
   **The same overhang pattern applies anywhere a pill sits in flowing text — flag to Loop 3.**
3. Comp-arithmetic deviations (not skeleton bugs; skeleton and real match exactly in all three):
   table panel renders 514 px, comp 03 says 512 (th select-all checkbox is 16 px > the 14 px
   type line, header row 33 not 31); stat card 118 vs comp 116 and meta card 358 vs comp 354
   (borders excluded from comp sums). Loop 3 should restate the comp numbers or shave the th.

### 3. Shimmer cost — **TESTED** (throttled via CDP) · one sub-claim PARTIAL

20 skeleton table rows + 4 stat cards + 6-field dl shimmering simultaneously; 10 s rAF
histogram, no evals during the sample window; painted into the in-page HUD (see
`skeleton-fpsrun-light.png`).

| CPU throttle | median fps | 1% low | frames/10 s |
|---|---|---|---|
| 1× (daemon) | 90.9 | 38.0 | 777 |
| 1× (playwright instrument) | 90.9 | 38.2 | 779 |
| **4× (`Emulation.setCPUThrottlingRate`)** | **91.7** | 38.2 | 773 |
| 6× | 90.1 | 38.2 | 769 |

**fps is invariant under CPU throttle** — the strongest available proof that the main thread is
not in the animation loop. Method: shimmer is one `::after` overlay **per card/panel — 6
compositor layers total, independent of row count** (verified: 6 running `t4shimmer` animations
at rows=20); animation touches `transform: translateX` only; `will-change:transform` (read back
via `getComputedStyle`). The identical ~38 fps 1% low at every rate (incl. unthrottled) is the
headless compositor's scheduling cadence, not load. Repeating-cost hygiene: the shimmer exists
only while `state=skeleton`; skeleton lifetime = query lifetime (04 comp, "bounded by
construction"), and the swap removes the animated layers outright — nothing loops on a loaded
screen.
**PARTIAL sub-claim:** "no paint work per frame" is inferred from throttle-invariance +
transform-only declaration; no DevTools paint-count trace was captured (the shared daemon's
CDP is pipe-only; my independent instance measured throttling but I did not add tracing).
**Absolute fps on a real mid-range Android was not measured** — 4× CPU throttle on an M4 is
the budget's proxy, per the dispatch's own protocol.

### 4. Byte cost — **TESTED**

| Asset | raw | gzip −9 |
|---|---|---|
| Skeleton CSS (`<style id="skeleton-css">` — the whole technique) | **1,064 B** | **646 B** |
| Whole prototype file | 91,393 B | ~56.7 KB |
| Whole file minus embedded font (the honest page weight) | 26,996 B | 7,273 B |
| Embedded Inter woff2 (prototype-only; production self-hosts the same repo asset) | 64,344 B (48,256 B binary) | — |

Library: **none**. Tier 1 holds with ~1 KB to spare against any budget.

## Fonts

Inter Variable rendered from the repo's own woff2
(`frontend/dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2`, base64-embedded so `file://`
can't block it) — verified via `document.fonts.check`, painted in every HUD. JetBrains Mono
Variable is **not in the repo yet**; the register's declared fallback (`ui-monospace`/SF Mono)
rendered for mono-caps labels and identifiers. Geometry consequence: none measured (line
heights are explicit; all 49 pairs at 0.00), but mono **glyph widths** will differ when JBMono
lands — block *widths* for mono text (th labels, identifiers, dt labels) should get a one-pass
re-tune then. That sub-claim is PARTIAL; heights and positions are TESTED and face-independent.

## States built

- `?state=skeleton` — all three regions as skeletons, shimmer running (motion permitting) — both themes ✓
- `?state=loaded` — the approved real content ($128,400 / 132 / 6 of 214 / $23,900; the 8 approved item rows incl. Draft-supersedes-stock; the 6-field bill dl, USD 54.00) — both themes ✓
- `?state=swap` — skeleton → loaded at 1500 ms, 120 ms opacity crossfade, `cubic-bezier(0.2,0,0,1)`, no movement — both themes ✓ (measured, screenshots via skeleton/loaded per dispatch)
- `?state=reduced` — designed still: static line-token blocks, zero animations (verified `getAnimations()` = 0); gated by **both** `prefers-reduced-motion` media query and `matchMedia` listener, forced via query param for deterministic shots — both themes ✓

**Not built, named:** the other five data states of the nine (empty, error, denied, offline,
stale, conflict, bulk, partial-beyond-loading) — T4 is the *loading* state technique; the
remaining states are owed by each surface's comp (02/03/04 §States, already specced there),
not by this prototype. No narrow-viewport run: these are fixed-width console regions (1120 px
main per register §4); the dispatch specifies 1440×900 only.

## Screenshots (all full-page at 1440 width, macOS M4, headless chromium)

- `shots/skeleton-skeleton-light.png` · `shots/skeleton-skeleton-dark.png`
- `shots/skeleton-loaded-light.png` · `shots/skeleton-loaded-dark.png`
- `shots/skeleton-reduced-light.png` · `shots/skeleton-reduced-dark.png`
- `shots/skeleton-fpsrun-light.png` — 20-row stress run with the fps/CLS/geometry HUD painted
  into the frame (the B=708 figure in that HUD is the stress harness's 12 extra skeleton rows,
  not the geometry contract, which runs at rows=8 and reads 0)

Every shot was opened and read back. HUD (fixed, bottom-right) paints state/theme/motion, font
status, CLS, per-region geometry deltas, fps, and skeleton CSS bytes into every frame so the
numbers survive the session.

## Register conformance notes

Line-token blocks (`--line`, both themes), r6 (r4 for the checkbox stand-in, r-full for pill
stand-ins — matching the real controls they hold the space of), shimmer only when motion is
allowed, never a spinner; th labels render real immediately (03 comp); pagination text hidden
with its 17 px height reserved. No invented content: all loaded-state data is the approved
frame's data verbatim. No provenance claims; no stand-in assets were needed.

## Caveats carried (none blocking)

1. Mono block widths re-tune when JetBrains Mono Variable lands (PARTIAL, widths only).
2. Loop 3: preload the Inter woff2 to kill the boot-time font re-metric (0.023 CLS artifact).
3. Loop 3: reconcile comp arithmetic (panel 512→514 or shave th checkbox; card 116→118;
   meta 354→358) and adopt the `small{line-height:1}` + pill-in-dd flex fixes — both are
   latent bugs in the approved-frame CSS itself, found by this instrument.
