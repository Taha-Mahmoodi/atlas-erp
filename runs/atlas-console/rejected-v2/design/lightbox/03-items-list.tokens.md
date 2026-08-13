# Composition sidecar — lightbox, Surface 3 of 7 (Items List)

**Composition anchor:** `dense-grid`
**Background mode:** `flat-surface`

Applies to both `03-items-list-light.md` and `03-items-list-dark.md` — the composition does
not change between palettes, only the fills do.

## Why these tokens

The working table takes the majority of the canvas (37-row `role="grid"`, 1136px of 1200px
content width, ~632px of visible vertical space before scroll) with the left rail and the
fixed glass command bar fully subordinate to it — the textbook `dense-grid` case this token
exists for. The substrate under all of it, rail included, is one flat unblurred fill with
assets (rows, chips, buttons) inline on it and zero image/gradient/texture — `flat-surface`,
plainly.

## Note on the anti-repeat check

Per this dispatch's instruction: `dense-grid` / `flat-surface` is the correct, expected
reading for this screen and is not being second-guessed against its table-heavy neighbor
(Surface 4, vendor bill detail). The set-level anti-repeat criteria are suspended for this
run — a tool-shaped console where the working table *is* the screen on multiple surfaces
should log the same honest tokens each time, not a manufactured alternate to satisfy a
variety check that doesn't apply here.

## Collision, reiterated for the record

Opaque plain data layer × liquid glass confined to exactly one object (the fixed command
bar). This surface is the clearest single proof of that boundary in the seven-surface set:
every pixel below `y=64px` — including all 37 rows — is flat and opaque; the only
`backdrop-filter` in the whole comp lives in the 64px band above it.

## What was decided, one line

Dense, real-count (37-row) opaque grid with status carried by shape+hue (never color alone),
sticky command bar and sticky table header both reserved as real space rather than floated,
and a single documented-pairing decision for dark mode's primary CTA (`accent-tint-dark` /
`accent-dark`, reused rather than inventing an unlicensed emphasis-grade fill DIRECTION.md's
dark table doesn't define).
