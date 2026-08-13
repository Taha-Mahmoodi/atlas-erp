# lightbox: Surface 2 of 7 — Role Home — composition sidecar

| Field | Value |
|---|---|
| Concept | lightbox |
| Surface | 02 of 07 — Role Home |
| Mode | coded comp (spec block) |
| Composition anchor | `left-rail-caption` |
| Background mode | `flat-surface` |
| Canvas | 1440×900 fixed, web/desktop-only |
| Platform mode | none (web/desktop-only surface) |
| Files | `02-role-home-light.md`, `02-role-home-dark.md` |

## What I decided

A narrow 240px flat rail (icon+label nav, Home active) against a wide 1136px worklist field —
`left-rail-caption` — deliberately **not** `dense-grid`: this is a plain single-column list of
line items grouped into three flat sections (Due today / Due this week / Everything else), never
a multi-column table, which is what keeps it legibly distinct from Surfaces 3/4 (the items grid
and the vendor-bill detail, both dense-grid tables). Every row is two lines of type (identifier +
counterparty, then one line of context) plus a right-hand value and a status dot — hierarchy from
size, weight, and space, zero cards, zero shadows, zero color-blocked lanes, per the collision.

This is also the anchor screen for the whole concept's one glass object: I defined the floating
command bar's exact position (`fixed, 0/0/1440/64, z-50`), fill/blur/border, and — the brief's
specific ask — the worst-case *scrolled* frame it needs to hold contrast against. At
`scrollTop: 228px` the resting layout's overdue/error-triangle row lands fully behind the bar,
blurred; I used that as the named worst-case frame rather than a hypothetical one, since it's the
highest-chroma content actually on this screen.

Two decisions beyond the literal brief:
1. **Icon-buttons on the bar (quick-create, notifications) are 44×44px, not 36×36px**, and the
   bar is a 64px edge-to-edge strip, not a floating rounded inset pill. Surfaces 3/5/6 (already
   on disk) each specify a different number for one or both of these — see "Constraints not
   fully satisfiable," below. I picked the values that match this run's own stated 44px
   primary-control floor (`ACCESS.md` row 1) rather than propagating whichever number happened
   to land first.
2. **The scrim rule is extended from text runs to icon-only controls** (the quick-create `+` and
   the notification bell both sit on the same scrim fill as the search trigger's label). The
   brief states the rule for text; an unlabelled glyph needs the same guaranteed contrast
   against a moving blurred background, so I applied it there too rather than leaving two
   controls on raw glass.

## Constraints not fully satisfiable

- **The glass bar's exact geometry is not consistent across this concept's own files.** Surface
  3 (Items List) already states "36×36px" icon buttons at this same 64px bar height. Surface 5
  (New item form) independently specifies a 56px bar with 44×44px controls. Surface 6 (Empty
  state) specifies a floating, rounded, 16px-inset 56px pill with a brand-mark wordmark this file
  doesn't include. I did not edit any of those files — out of this dispatch's scope — and I did
  not silently match their numbers either, since two of the three disagree with the run's own
  stated 44px floor. This file's numbers are the canonical ones per its "anchor screen" brief;
  the three deltas are named here explicitly for Loop 2 to reconcile in one pass rather than
  discovered piecemeal at Gate A.
- **Dark-mode scrim value is derived, not given.** `DIRECTION.md` §7 states the *rule*
  ("same scrim rule, re-measured on dark") but not a number. I constructed one by the same
  method the light value used (panel's base hue at a higher opacity than the panel itself) and
  flagged it inline in the dark file — treat it as a placeholder for a real Loop 2 pass, not a
  measured value.
- **All status-dot and glass-panel contrast ratios on this screen are estimated**, per this run's
  own §11 coded-comp disclosure — none are script-verified. The pending/amber hue (80°) is
  flagged as the likeliest to actually fail the 3:1 graphical floor once measured for real.
