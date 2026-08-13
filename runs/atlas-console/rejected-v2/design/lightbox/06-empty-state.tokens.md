# lightbox: Surface 6 of 7 — Empty State (Filtered) — composition tokens

Same composition serves both `06-empty-state-light.md` and `06-empty-state-dark.md` — only
color retunes between them, per `DIRECTION.md` §7's "one design in two palettes" rule.

- **Composition anchor:** `centered-statement`
- **Background mode:** `flat-surface`

**Why these two.** The one thing the eye lands on is the single centered sentence sitting in
the body region the empty grid would otherwise fill — everything above it (rail, glass bar,
h1, filter chips, table header) is subordinate framing that explains *why* that sentence is
there, not competing content, which is `centered-statement` rather than `dense-grid` (the
token this same surface's populated sibling, 03, would log). This is deliberately the calmest
screen in the seven alongside login (01) and the error state (07) — the run's own instruction
that this state read as visibly different from the dense worklists and tables that dominate
the rest of the set, and different in particular from its own screen's normal (populated)
state, which is a `dense-grid` composition under the identical chrome.

The substrate is one flat solid fill behind rail, bar-well, and content alike — no image, no
gradient field, no texture — which is `flat-surface`. The one glass object on the canvas (the
floating command bar) is a foreground control per the concept's collision, not part of what
"background mode" describes; the substrate underneath and behind it stays flat regardless.

**Filtered vs. true-empty, logged as one surface.** Both variants share this exact anchor and
background mode — the fix for the live defect is the presence/absence of the filter-chip row
and a swapped one-line message, not a different composition. A worker or reviewer diffing this
surface against its neighbors should read `centered-statement` / `flat-surface` for either
variant.
