# SKIPS.md — atlas-console (append-only)

## 2026-08-14 — Gate B interactive review waived by the human, in advance

Taha, before Loop 2 returned: "gate b is approved when it is done, when it is done do all
the PR shenanigans." Recorded per §16: skipping is allowed, silent degradation is not.

**What this waives:** the interactive review of the Gate B package (technique set, verdicts,
budgets) before proceeding.

**What it does not waive:** if the package lands with a non-trivial adverse finding — a
technique that failed outright, a budget blown, a contrast pair that can't be fixed with a
token nudge — that gets surfaced to Taha before the affected piece ships, per §16's
non-trivial-finding clause. Routine cuts and ship-with-caveat verdicts proceed under this
approval.

**Follow-on instruction attached to the same message:** once Loop 2 is done, commit the run
deliverables to the atlas-erp repo via the project's GitHub workflow (feature branch → PR to
dev → merge on green CI, per GITHUB-WORKFLOW.md and the standing PR-merge authorization).

## 2026-08-14 — Gate B closed under the pre-approval above

Package: 4 techniques ship, 1 ship-with-caveat (glass ⌘K palette), 0 cuts. No outright
failure, no blown budget — the pre-approval applies. Decisions taken at closure, recorded
here rather than re-asked:

1. **Chart gray → `bar-lo` accepted** (the conductor's recommendation). The as-approved
   line-gray measured 1.21:1 against the 3:1 non-text floor; `bar-lo` (#939599 light /
   #66676b dark) is boundary-verified at 3.000+. This is the token-nudge category the
   pre-approval covers; both variants are screenshotted in `prototypes/shots/` if Taha ever
   wants to compare.
2. **The two PARTIAL claims are bought, with named re-test triggers:** (a) glass on low-end
   Windows iGPU — untestable on this hardware; the designed floor (opaque panel, built,
   pixel-verified) bounds the risk; re-test lands at build QA on fleet hardware. (b)
   status-pill scroll on mid-range hardware — INFERRED beyond the measured M4 numbers;
   re-test at build QA.
3. **Binding constraint from T1 carried into the record:** ink-only text on glass (ink2 on
   glass measured 3.98 light — fails); ink2 permitted only on opaque backings.
4. **The seven §16 deferral rows** from DIRECTION.md §21 are carried as deferred-with-cost,
   verbatim by reference: chart-gray choice (closed above), fleet-iGPU measurement, JBM
   vendoring + subset weigh-in, the never-held operator interview (all §13.1 counts are
   seed-data estimates), DPR-2 crispness, the three-question re-run with real data at Loop
   4, and per-operator column configuration. None block the handoff; each names where its
   cost lands.
