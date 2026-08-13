# the yard: Surface 7 of 7 — Error State — composition sidecar

**Composition anchor:** `centered-statement`
**Background mode:** `flat-surface`

## Why

Anchor and background mode were both fixed by the dispatch brief itself ("centered-statement
composition, calm register matching the empty-state screen (surface 6), distinct from the
dense-grid table screens") rather than picked freely from the menu — logged here verbatim so
the conductor's set-level check has both tokens regardless of source.

`centered-statement` fits mechanically as well as by brief: one block (torn token + h1 +
message + action) sits on the canvas axis, the rail and header are present and functional but
carry nothing that competes for the eye — no metric numbers, no second card, no lane grid.
That is the opposite composition from surfaces 02 (bento lanes), 03/04 (dense-grid), which is
the differentiation this token records.

`flat-surface` follows from the concept's own rule ("no glass... soft drop shadows") and from
the calm register asked for: one solid substrate, the error card is one more flat asset resting
on it, no gradient/texture/image doing the work a plain sentence should do instead.

## What this screen does that its likely neighbors don't

- Surfaces 03/04 (items list, vendor bill detail) are `dense-grid` by necessity — real
  `role="grid"` tables, forty-row density. This screen is the one place in the set with a single
  paragraph of copy and one button
- Surface 02 (role home) is a bento grid of unequal lanes with metric numbers everywhere; this
  screen deliberately shows zero numbers and zero lane cards
- Surface 06 (empty state, filtered) is the nearest sibling in register — also calm, also a
  single centered message — but its token is a dashed-outline empty slot ("no items yet,"
  advisory, reversible-by-filtering), while 07's token is the concept's one and only *torn*
  token, an imperative alert, not an advisory empty state. Same family, deliberately different
  urgency and a shape that exists nowhere else in the run

## Open flags carried from the two spec files (not resolved by DIRECTION.md, decided here)

1. Dark-mode "Back to items" button fill has no stated emphasis token — filled with
   `accent-dark` + dark-substrate-colored label (~10:1), not a straight recolor of the light
   accent-emphasis + white pairing.
2. Dark-mode focus ring has no stated accent-ink-dark token — substituted `accent-dark` for
   `accent-ink` because accent-ink's L0.44 does not reliably clear 3:1 against the dark
   card/substrate (L0.19–0.24).

Both are logged in `07-error-state-dark.md` §4 with the reasoning; neither is silently shipped.
