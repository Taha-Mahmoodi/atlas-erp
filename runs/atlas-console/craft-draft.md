# craft-draft.md — atlas-console Loop 2 (craft-conductor working record) — COMPLETE

Gate A DECIDED: porcelain, conformance-to-approved-register. Loop 2 ran 2026-08-14;
worker-recorded timestamps 03:22:10 → 03:50:10 +0430 (conductor is clockless on this
harness — Read/Write/Agent only, no Bash; timestamps are from worker verdict `date` lines,
a recorded deviation from the loop file's timekeeping rule).

## Phase 1 — assignments (written before dispatch; unchanged)

Arsenal groups, by name: **CSS and SVG native** + **Information design**. Nothing from
Rendering/GPU or Post-processing. Budget spent on the operator's 40×/day objects (03,
⌘K palette, 02); 01/05/06/07 quiet by decision. Three-question answers per technique were
recorded in this file pre-dispatch and are preserved in each verdict file and
DIRECTION.md §15/craft history.

## Phase 2 — verdicts (full records on disk beside each prototype)

| # | Technique | Verdict | Evidence | Bytes (raw/gz) | Verdict file |
|---|---|---|---|---|---|
| T1 | glass ⌘K palette | **ship-with-caveat** — ink2 never directly on glass (worst-case rendered 3.98 light / 4.59 dark); ink passes 8.02 / 5.00 | TESTED (rendered contrast, fps @4× CPU 89.3/88.5 median, keyboard pass, bytes) · PARTIAL (low-end GPU fleet; floor = opaque panel, built + cmp-identical to reduced) | 3,567 / 1,310 | prototypes/glass-palette.verdict.md · 03:22:10–03:50:10 |
| T2 | sparklines | **ship** | TESTED (stroke = token exact, 0px layout delta, 209 B/el) · PARTIAL (DPR-2 — no instrument) | 8,666 / 2,544 file | prototypes/sparklines.verdict.md · 03:22:29–03:48:39 |
| T3 | monochrome paired bars | **ship** — recommends bar-lo (#939599 → 3.0002 light, #66676b → 3.0081 dark) over approved line-gray (1.21/1.22 — FAILS 3:1); Gate B chooses, both screenshotted | TESTED | 7,603 / 2,336 file | prototypes/bar-chart.verdict.md · 03:22:55–03:30:10 |
| T4 | skeleton match | **ship** | TESTED (CLS 0 incl. 4× throttle; geometry Δ 0.00px ×49 pairs; shimmer 90.9/91.7/90.1 fps @1×/4×/6× — throttle-invariance = compositor proof) · PARTIAL (no paint-count trace) | 1,064 / 646 CSS | prototypes/skeleton.verdict.md · lock 03:37:56–03:48:09 |
| T5 | status pills @ density | **ship** | TESTED (rows 65/59, pill 24 exact, 11 contrast pairs script-confirmed, rendered pixels = tokens) · PARTIAL (fps unthrottled 77.7/79.4 mean) · INFERRED (mid-range no-jank) | 506 / 280 pill CSS | prototypes/status-pills.verdict.md · 03:23:38–03:49:32 |

No cuts. Machine for all numbers: Apple M4, macOS 26.5.2, headless Chromium, 1440×900
@ DPR 1. Contrast queue from Loop 1 CLOSED by T5: ink-on-acc-t 15.62 / 12.93; thin trio
exactly 4.580 / 4.542 / 4.814 (no headroom — any tint change re-runs the script).

Browse-daemon serialization held: mkdir lock, one >10-min stale lock stolen and logged
(T1), one 13–16 min queue wait (T2/T5), daemon never killed.

## Phase 3 — motion spec: final in DIRECTION.md §16 + tokens.json `motion` (unchanged
from pre-dispatch draft; T1/T4 implemented and measured it as specced).

## Phase 4 — budgets: final in DIRECTION.md §17. Measured inputs: Inter latin woff2
48,256 B on disk (TESTED); JBM absent from repo (subset INFERRED, tier-2 contingency
pre-decided); technique CSS sums ≈5.5KB raw inside the shell CSS line.

## Phase 5/6 — deliverables

- DIRECTION.md — COMPLETE (Part I direction amended ◆, Part II craft: TOOLS §13 nine,
  seven-state control table, elevation, icons, grid, motion, budgets, broken-rules (1 row),
  §16 deferral table, build notes, handoff clause, honest-residue §23–25)
- tokens.json — COMPLETE (DTCG CG Draft 2026-07-30 pinned; both themes; bar-lo marked
  Gate-B-pending; motion as transition tokens with aliases)
- Gate B package — assembled in the conductor's return message. Conductor holds no gate;
  the main session presents to Taha.

## Open items that belong to the gate or the build (not to this loop)

1. Gate B choice: bar-lo vs as-approved chart gray (recommendation: bar-lo; keeping
   approved gray adds a broken-rules row).
2. Build: 10 prototype-discovered corrections (DIRECTION.md §20).
3. Build: vendor JBM + subset weigh-in; §7 vendoring (nothing to vendor from prototypes —
   zero libraries used).
4. Fleet-hardware glass measurement at build QA (T1 PARTIAL residual).
