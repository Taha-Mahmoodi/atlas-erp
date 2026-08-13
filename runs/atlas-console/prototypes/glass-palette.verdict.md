# T1 — glass ⌘K command palette (porcelain) — VERDICT

- Run start: Fri Aug 14 03:22:10 +0430 2026
- Run end: Fri Aug 14 03:50:10 +0430 2026
- Prototype: `runs/atlas-console/prototypes/glass-palette.html` (standalone, no build step; states via `?theme=light|dark&state=actions|query|empty|reduced|nofilter`, plus `&probe=1` contrast probe, `&worst=1` worst-case underlay, `&hud=1` fps readout, `&anim=blur` record-only blur-animated enter)
- Machine: Apple M4 (Mac16,10, 10-core), macOS 26.5.2. Viewport 1440×900 @1x devicePixelRatio for every figure and screenshot.
- Browsers: gstack browse daemon (bundled headless Chromium) for screenshots/keyboard/unthrottled fps; own headless Chrome 151.0.7922.109 + CDP for throttled fps. Served over `http://127.0.0.1:8377` (python3 http.server) so the repo Inter woff2 loads.

## VERDICT: **ship-with-caveat**

The technique holds. The caveats are exact:

1. **No ink2 (secondary) text on the glass surface without a backing.** Rendered worst-case measurement (max-contrast register content directly behind the glass): the empty-state 12px ink2 hint fails the 4.5 floor in light — **3.98** vs worst rendered pixel (4.09 vs mean) — and is at-floor in dark — **4.59** worst (4.87 mean). Primary ink text passes everywhere (min **5.00**). Fix options for Loop 3, in register vocabulary: back text zones opaquely (the highlighted-row treatment, 85% card, measured 16.41/13.37, is already sufficient), add the scrim the register's §3 focus-ring note already contemplates ("scrim guarantees composite"), or use ink instead of ink2 for on-glass secondary text. The palette spec itself is unchanged.
2. **Fleet frame-rate claim is PARTIAL, by construction.** Everything measured is Apple M4. The 4× CPU throttle was verified genuinely engaged (busy-loop benchmark 8188→1914 Mops = 4.28× reduction) and the palette still held ~88 fps median — but CPU throttling cannot exercise the GPU compositor cost of `backdrop-filter`, and the realistic ERP fleet's low-end Windows iGPU cannot be tested on this machine. The designed floor for weak GPUs is the same opaque panel as reduced motion — built, screenshotted, and pixel-identical to the `nofilter` fallback (cmp-verified per theme).
3. **Constant-blur enter is the spec and stays the spec.** The record-only blur-animated variant showed no penalty on M4 (a GPU-strong machine cannot expose its cost); this is not evidence it is safe on the fleet. INFERRED from Chromium rendering docs and the M4 measurement's inability to falsify: animating backdrop-filter re-evaluates the filter chain per frame and is the known-worse path on weak GPUs.

## Three-question answers (carried from dispatch)

1. **Understand:** the palette is a transient command layer OVER the work — data stays visible through it, so a command never feels like leaving the screen.
2. **Day shorter:** ⌘K jump is the highest-frequency navigation act (~30×/day); removes the sidebar round-trip and the mouse.
3. **Cost:** ~0 extra library bytes (CSS-native, tier 1); component measures 3,567 B raw / 1,310 B gzip. GPU cost of blur-over-scroll was the unknown → measured below.

## Measurement 1 — RENDERED text contrast vs worst-case busy frame — **TESTED**

Method: `?probe=1` renders the identical layout with palette text transparent; the PNG region behind each text run (element rects reported by the page, dpr 1) is analyzed with PIL; worst pixel = minimum WCAG 2.x ratio vs the text color. Two underlays measured:

**(a) Approved busy frame** (dense 40-row items table, tinted pills, mono identifiers, 4 stat cards): matches the model.
| | light (ink #17181c) | dark (ink #eeeef2) | modeled (§1) |
|---|---|---|---|
| min over rows | **17.44** | **14.67** | 17.29 / 15.17 |
| kbd chips (opaque card fill) | 17.74 | 14.68 | — |
| empty statement (ink) | 16.99 | 14.15 | — |
| empty hint (ink2) | 5.02 | 6.22 | — |

**(b) Worst case** (`?worst=1`: register-legit ink buttons, 26px/650 stat value, dense 15px/650 ink text placed DIRECTLY behind the palette text rows — the tail frame the floor exists for):
| region | light | dark | floor | result |
|---|---|---|---|---|
| row over solid ink/inverse button | **8.02** | **5.00** | 4.5 | PASS |
| other rows | 14.08–16.41 | 10.72–13.37 | 4.5 | PASS |
| highlighted row (85% card) | 16.41 | 13.37 | 4.5 | PASS |
| kbd chips (opaque) | 17.74 | 14.68 | 4.5 | PASS |
| empty statement 15px ink | 11.39 | 8.09 | 4.5 | PASS |
| **empty hint 12px ink2** | **3.98** (4.09 mean) | **4.59** (4.87 mean) | 4.5 | **FAIL light / at-floor dark** |

The modeled 17.29/15.17 is confirmed accurate for the calm composite it modeled (62% card over bg) and **optimistic by ~2–3× for worst-case content behind the glass**. Ink text never approaches failure; ink2 on glass does. No scrim was used — §3's component spec lists none; a scrim is the obvious lever if Loop 3 wants ink2 on glass.
Label: **TESTED** (M4, 1440×900@1x, headless Chromium, PIL pixel analysis). Not sampled separately: the query-input's own typed text (13.5px ink — bounded by the ink results above, same geometry).

## Measurement 2 — frame rate, palette open, blur active, underlay scrolling (rAF-driven, ~10s each) — **TESTED on M4; fleet claim PARTIAL**

In-page rAF delta histogram; median/mean/1% low/worst/dropped(>25ms) painted into a fixed readout so the screenshots carry the numbers.

| condition | median | mean | 1% low | worst ms | dropped |
|---|---|---|---|---|---|
| scroll, unthrottled, light (browse Chromium) | 76.3 | 79.2 | 38.0 | 32.9 | 96/704 |
| scroll, unthrottled, dark | 75.8 | 78.8 | 38.2 | 37.4 | 95/701 |
| **control: scroll, NO palette, unthrottled** | 80.6 | 81.7 | 38.0 | 29.3 | 91/725 |
| scroll, **4× CPU throttle**, light (Chrome 151) | **89.3** | 85.3 | 38.3 | 35.5 | 90/752 |
| scroll, **4× CPU throttle**, dark | **88.5** | 85.1 | 38.2 | 49.2 | 88/751 |
| control: NO palette, 4× throttle | 86.2 | 84.1 | 38.2 | 43.2 | 91/742 |
| enter (a) SPEC opacity+scale const-blur, unthrottled | 80.6 | 81.6 | 38.2 | 26.3 | 91/725 |
| enter (b) BLUR-ANIMATED 0→18px, unthrottled | 75.8 | 78.3 | 38.0 | 27.8 | 96/696 |
| enter (a) SPEC, 4× throttle | 88.5 | 85.3 | 38.3 | 129.1 | 90/746 |
| enter (b) BLUR-ANIMATED, 4× throttle | 90.9 | 86.8 | 38.2 | 126.4 | 86/740 |

Reading the numbers honestly:
- Throttle verified real: `Emulation.setCPUThrottlingRate(4)` measured 4.28× on a busy-loop (8188→1914 Mops). Headless rAF is not vsync-locked here (~76–90 median), so medians compare conditions rather than promise a 60Hz wall-clock.
- **The blur adds ≈0–4 fps median and does not move the tail at all**: 1% low (38) and dropped counts are identical with the palette hidden — the tail is headless scheduler noise, not blur cost.
- 4× CPU throttle barely moves anything → the palette's cost is compositor/GPU-side, not main-thread. That is exactly why the fleet claim caps at **PARTIAL**: a weak Windows iGPU is the untested risk, and its designed floor is the opaque panel (`nofilter` state, identical to reduced).
- enter (b) worst-frame spikes under throttle (126–129ms) occur at animation-restart boundaries in the harness loop for both (a) and (b); no separation measurable on M4. Spec keeps constant blur on Chromium-docs reasoning (INFERRED), not on this non-measurement.

## Measurement 3 — byte cost — **TESTED**

- Palette component (CSS + markup, minified): **3,567 B raw / 1,310 B gzip** (CSS 2,780 + HTML 787). Tier 1 as assigned; zero library bytes; no JS required for the visual (JS in prototype is semantics + test harness).
- Whole prototype file (incl. underlay, harness, worst-case rig): 24,120 B raw / 7,692 B gzip.

## Measurement 4 — keyboard pass — **TESTED** (real CDP key events via `browse press`)

| check | result |
|---|---|
| Enter on invoker opens; focus → input (query) / listbox (actions) | PASS |
| ArrowDown moves aria-activedescendant opt0→opt1; ArrowUp wraps to opt3 | PASS |
| Tab trap: input ↔ listbox, focus never leaves dialog | PASS |
| Esc closes (display:none after 110ms exit) | PASS |
| Esc returns focus to invoker | PASS |
| role="dialog" aria-modal + combobox/listbox/option + aria-selected wired | PASS (markup verified) |

## States built (each × light + dark, screenshot at 1440×900@1x)

`actions` (4 rows, Receive stock highlighted) · `query` (input "rec" + 4 filtered rows; open height 198→242 as ruled) · `empty` ("No results for “xq-914”." + ink2 hint) · `reduced` (instant, fully opaque card panel — designed state, ships in Gate B package) · `nofilter` (@supports author-fallback-first; **pixel-identical to reduced, cmp-verified, kept as separate files**). Reduced-motion honored via media query AND matchMedia listener; motion spec implemented exactly (160ms enter cubic-bezier(.2,0,0,1) opacity+scale, constant blur; 110ms exit opacity-only).

**Not built, named:** the nine tool-shaped data states beyond the palette's own empty (loading, partial, error, denied, offline, stale, conflict, bulk) — they belong to the surfaces the palette floats over, per this dispatch's owed-state list; palette result-loading was not in scope. Live-app underlay (localhost:5173) not attempted — optional; the synthetic worst case is stricter and was the required one. 390px-wide pass not owed for this floating layer by dispatch (desktop console); flag if Gate B wants it.

## Screenshots (`runs/atlas-console/prototypes/shots/`)

- `glass-palette-{actions,query,empty,reduced,nofilter}-{light,dark}.png` — 10 design states
- `glass-palette-actions-{light,dark}-worstcase.png` — palette over the worst-case ink content (inspectable basis of Measurement 1b)
- `glass-palette-fps-scroll-unthrottled-{light,dark}.png`, `glass-palette-fps-scroll-4x-{light,dark}.png`, `glass-palette-fps-enter-{spec,blur}-4x-light.png` — fps readouts painted in-page

## Fonts

Inter Variable loaded from the repo woff2 (`document.fonts.check` true) — type-accurate. JetBrains Mono Variable: **not in repo**; `fonts.check` returned true on this machine (likely system-installed), so chips/identifiers may have rendered in the real face here but that is not guaranteed on the fleet → mono-glyph-sensitive claims are **PARTIAL**; contrast numbers are color-based and unaffected. §2's subset-to-repo task stands for handoff.

## Protocol log

- Browse lock: acquired 03:30:47 after waiting out another holder; released 03:37:55. Re-acquisition for worst-case shots: waited on a live lock (346s), then removed a **stale lock >600s at 03:47:58 per protocol** and acquired; my lock was removed by another party before my `rmdir` — all outputs from that window were verified consistent (file sizes, rect JSONs, visual crops) before use. Daemon never killed or restarted. One stray `browse perf` ran pre-lock during `--help` discovery (read-only, no navigation).
- No remote pushes, no deploys, no vendoring, DIRECTION.md untouched.

## Evidence-label summary

| claim | label |
|---|---|
| Rendered contrast, both themes, calm + worst-case | TESTED |
| fps on Apple M4, unthrottled + verified 4× CPU throttle | TESTED |
| Fleet-wide (low-end Windows iGPU) frame rate | PARTIAL — untestable here; opaque floor designed & built |
| Constant-blur > animated-blur on weak GPUs | INFERRED — M4 cannot expose the difference |
| Byte cost | TESTED |
| Keyboard/semantics pass | TESTED |
| Mono face fidelity on fleet | PARTIAL |
