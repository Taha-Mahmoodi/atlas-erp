# the yard: Surface 7 of 7 — Error State (Record Not Found)
**Mode:** Dark · **Canvas:** 1440×900 fixed desktop viewport · Web/desktop-only · Coded-comp spec

Same design as the light spec — one design in two palettes, not two art directions. Only
lightness/chroma retune; the layout, the type table, the torn-token construction, and the
access behavior below are unchanged from `07-error-state-light.md`. This file states the
recolor and the two places dark mode required a decision the light spec's tokens didn't fully
cover.

---

## 1. Layout — 1440×900

Identical region bounds to the light spec: rail `0,0,240,900` · sticky header `240,0,1200,56`
· content area `240,56,1200,844` · error card `560,273,560,410` (centered both axes within the
content area). Same internal stack, same 64px card padding, same 24/12/8/32px gaps.

**Composition anchor: `centered-statement`** (unchanged). **Background mode: `flat-surface`**
(unchanged) — flat dark substrate behind rail, header, and content; the card is one flat asset
on it, no gradient, no image.

Card container: `card` (dark) fill, `border-radius: 24px`, 1px `hairline` (dark) border —
decorative, paired with the shadow, never the sole boundary — + soft drop shadow, darkened and
lower-opacity so it reads as lift rather than a light-mode shadow pasted onto a dark surface:
`0 8px 24px -8px oklch(0 0 0 / 0.45)`.

---

## 2. Type table

Unchanged from light — same faces, sizes, weights, line-heights: title 20/600, body/data
14/450, meta 12/450, mono-identifier 13/500 (JetBrains Mono Variable), button-label 16/600
(Inter Variable). Type never recolors structurally between modes, only the palette it sits on
does.

---

## 3. Torn signal-token

Same 96×96px squircle, same jagged bottom-right tear geometry, same glyph position and
accessible name (`"Error — item record not found"`) as the light spec. Recolored per the
concept's own dark Overdue/Error row:

- **Fill:** `oklch(0.65 0.17 25)`
- **Glyph:** dark exclaim mark `oklch(0.16 0.02 25)` (not white — the dark-mode Overdue/Error
  pairing inverts to a dark glyph on the lighter-relative-to-substrate fill, matching the
  concept's status-token table exactly)
- **Torn edge:** exposes the dark `card` fill behind it, same construction as light

---

## 4. Palette — dark (from DIRECTION.md §6)

| Token | Value | Role here | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | content-area fill, rail fill | text-primary | ~14:1 |
| card | `oklch(0.24 0.012 290)` | error card fill | text-primary | ~13:1 |
| text-primary | `oklch(0.94 0.008 290)` | h1, breadcrumb current | on card/substrate | ~13:1 / ~14:1 |
| text-secondary | `oklch(0.68 0.015 290)` | body message, meta label, mono ID, breadcrumb link | on card | ~6:1 |
| hairline | `oklch(0.34 0.015 290)` | card border — decorative only | — | non-load-bearing |
| accent-dark | `oklch(0.76 0.14 290)` | breadcrumb-link hover/focus color, "Back to items" button fill (see below), focus ring (see below) | on substrate | ~6:1 |
| accent-tint-dark | `oklch(0.30 0.05 290)` | not used on this screen | — | — |
| Overdue/Error hue (dark) | `oklch(0.65 0.17 25)` / `oklch(0.16 0.02 25)` | torn token fill / glyph | — | per concept status table |

### "Back to items" button — dark fill, a stated deviation

DIRECTION.md's dark palette gives one accent role (`accent-dark`), not a separate ink/emphasis
split the way light mode does. Reusing `accent-dark` as a solid button fill with a **white**
foreground (mirroring light mode's accent-emphasis + white) would under-contrast — accent-dark
is a *light* purple (L 0.76) meant to sit legibly *on* the dark substrate as foreground text,
not to carry white text on top of it.

**Decision (not explicitly stated in DIRECTION.md, flagged here):** fill the button with
`accent-dark oklch(0.76 0.14 290)` and set the label in `substrate oklch(0.19 0.012 290)` —
reusing the already-defined dark substrate value as a near-black-purple foreground. The
lightness gap (0.76 vs 0.19) is large; estimated ratio **~10:1**, comfortably clear of 4.5:1
with no borderline caveat needed, so the button label stays at the same 16px/600 as the light
spec for cross-mode consistency rather than because dark mode requires the size floor.

### Focus ring — dark, a second stated deviation

The task brief's blanket ring spec ("2px solid accent-ink, 2px offset") names a token that only
exists in the light palette. Applying `accent-ink oklch(0.44 0.15 290)` unmodified against the
dark card (`L 0.24`) / substrate (`L 0.19`) is too close in lightness to reliably clear the
3:1 non-text-contrast floor WCAG 1.4.11 sets for focus indicators.

**Decision (flagged, not DIRECTION.md-stated):** dark-mode focus ring uses `accent-dark
oklch(0.76 0.14 290)` in place of accent-ink — the token already defined as this palette's
foreground-on-dark accent, filling the role accent-ink fills in light mode. Same weight and
offset: `2px solid accent-dark, 2px offset`, on the alert wrapper (unconditional on mount,
same reasoning as light) and on the button/skip-link's `:focus-visible` state.

---

## 5. Access

Identical structure and behavior to the light spec: skip link → rail → header → `<main>` with
one `<h1>`; alert-wrapper `role="alert" aria-live="assertive"` around h1 + message; `tabindex
="-1"` + programmatic focus on mount as the second channel; unconditional focus ring on mount
(color per §4 above); 44px button floor; no motion to reduce. See the light spec §5 for the
full rationale — nothing here changes except the two color substitutions logged in §4.

---

## 6. Content direction

Unchanged from light: one plain sentence stating what happened and that nothing changed, one
unambiguous next action. Copy does not recolor.
