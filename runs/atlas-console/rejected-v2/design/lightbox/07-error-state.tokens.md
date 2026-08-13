# lightbox: Surface 7 of 7 — Error State (Record Not Found) — composition tokens

Same composition serves both `07-error-state-light.md` and `07-error-state-dark.md` — only color
retunes between them, per `DIRECTION.md` §7's "one design in two palettes" rule for the opaque
layer.

- **Composition anchor:** `centered-statement`
- **Background mode:** `flat-surface`

**Why these two:** inside the shared app shell (left rail + glass command bar, unchanged from
every other surface in this concept), the entire content region has exactly one block on it — the
error message and its recovery link, centered on both axes within the content region — with
nothing else competing for attention. That is `centered-statement` by the token's own definition,
not `stacked-center` (which reads as a bare vertical run with no single dominant block) and not
`full-field` (there is no image or field filling the canvas — the substrate is a flat color, and
the message is a small centered object on it, not an overlay on a visual). The substrate behind
everything is one solid flat fill, unbroken by texture, gradient, or image, with the message block
as the only asset inline on it — `flat-surface` by the same literal reading used on every other
opaque-layer surface in this concept.

**Why this reads as distinct from its neighbors, not a repeat:** surface 6 (empty state) shares
both tokens — deliberately, since the brief asks this screen to match surface 6's calm register
exactly, and both are genuinely the same composition shape (one flat centered line replacing a
grid's normal content). Surfaces 2–5 (role home, items list, vendor bill detail, new item form)
are `dense-grid` and `right-rail-caption` — a working table or a populated form dominates the
frame. Surfaces 6 and 7 are the two places in the set where the frame is deliberately emptied out
instead, and logging the same pair of tokens for both is the honest record of that, not a failure
to vary — per this file's own instruction that a repeat where sameness is the design is a true
signal, not noise for the set-level check to catch.

**One divergence from a literal reading of surface 6, stated:** surface 6 kept the page `h1` as
"Items" (the list's identity persists through a zero-row filter) and rendered its empty-line as a
non-heading `<p>`. Surface 7's message *is* the page's `h1` — there is no valid record left to
title the page after, so the failure itself takes the heading role, and focus lands there
directly on render per the assertive live-region requirement. The composition tokens are
identical; the accessibility-tree structure underneath them is not, and that difference is
recorded in the surface files themselves, not smoothed over here.
