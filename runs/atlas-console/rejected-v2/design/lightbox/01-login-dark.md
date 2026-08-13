# lightbox: Surface 1 of 7 — Login (dark)

**Job:** identical to the light spec — get a known user from unauthenticated to inside their
Atlas workspace in the fewest moves, zero visual noise before they're in.

**Concept restraint, applied literally to this screen:** same as light — the glass command bar
doesn't exist pre-auth, so this surface has **no glass anywhere**, in either mode. Layout,
structure, and copy are identical to the light spec; only the palette and the resulting
foreground/background pairings change. This is "one design in two palettes," per the collision
sentence's own framing for the opaque layer — this file changes values, not the design.

**Canvas:** 1440×900, fixed, web/desktop-only. Same as light.

---

## Layout — numbers

Identical stack, identical spacing, identical 360px column centered at `x:540–900`, block top
`y ≈ 260px`. Only the fill and the skip-link border swap to the dark tokens below. See the light
spec for the full row-by-row layout table — not re-derived here since nothing about the geometry
changes between modes.

Substrate fill: `oklch(0.155 0.01 290)`, full canvas.

Skip-to-content link: same position and behavior as light (`x:16 y:16` on focus), border
`hairline` dark value, background `substrate` dark, text `text-primary` dark.

---

## Type table

Same faces, sizes, weights, line-heights as light — only color changes:

| Role | Face | Size | Weight | Line-height | Color |
|---|---|---|---|---|---|
| Wordmark | Inter Variable | 14px | 600 | 24px | `text-primary` (dark) |
| h1 (title) | Inter Variable | 20px | 600 | 28px | `text-primary` (dark) |
| Support line (body) | Inter Variable | 14px | 450 | 20px | `text-secondary` (dark) |
| Field label (meta) | Inter Variable | 12px | 450 | 16px | `text-secondary` (dark) |
| Field value (body) | Inter Variable | 14px | 450 | 20px | `text-primary` (dark) |
| "Forgot password?" (meta) | Inter Variable | 12px | 450 | 16px | `accent-dark` |
| Button label (body) | Inter Variable | 14px | 600 | 20px | substrate-dark (dark text on light-accent fill) |

---

## Color pairs — measured/estimated (per §11 disclosure)

| Pair | Foreground | Background | Ratio | Used for |
|---|---|---|---|---|
| text-primary / substrate | `oklch(0.95 0.006 290)` | `oklch(0.155 0.01 290)` | ~15:1 | h1, field values, wordmark |
| text-secondary / substrate | `oklch(0.70 0.014 290)` | `oklch(0.155 0.01 290)` | ~6:1 | support line, field labels |
| accent-dark / substrate | `oklch(0.77 0.13 290)` | `oklch(0.155 0.01 290)` | ~6.5:1 | "Forgot password?" link, focus ring |
| substrate-dark / accent-dark (button fill) | `oklch(0.155 0.01 290)` | `oklch(0.77 0.13 290)` | not stated in `DIRECTION.md` §7 dark table; estimated ≥6.5:1 by the same lightness-gap logic as the accent-dark/substrate pairing above — **not independently re-derived, flagged per §11**, re-measure at build | Primary CTA fill + label |
| hairline | `oklch(0.33 0.014 290)` | — decorative-only | n/a | input borders, skip-link border |

Dark mode has no `accent-emphasis` equivalent listed in `DIRECTION.md` §7 — only `accent-dark`
and `accent-tint-dark` exist for this palette, and neither is used at a borderline ratio here.
The button uses `accent-dark` as a **light fill with dark text** (light-accent-on-dark-substrate
is the whole point of the dark accent token), which is the opposite fill/text relationship from
light mode's dark-fill/white-text button — both read as "the one saturated object on an
otherwise neutral screen," which is the intended visual constant across the two palettes.

---

## Component notes

Identical component behavior to the light spec (same `autocomplete` values, same "never block
paste" requirement, same show/hide toggle, same native form submit) — only the color mapping
changes:

- **Focus ring** — `2px solid accent-dark` (dark mode's accent-ink-role token — `DIRECTION.md`
  §7 doesn't name a separate "focus" token per mode, so this maps the access brief's generic
  "accent-ink" requirement onto whichever mode's accent swatch actually exists), `2px offset`,
  `:focus-visible` only. Applied to the same five elements as light: both inputs, the show/hide
  toggle, "Forgot password?", the submit button, the skip link.
- **Primary CTA "Sign in"** — `<button type="submit">`, 44px height, full 360px width,
  `accent-dark` fill, `substrate`-dark colored label (dark text on the light accent chip — see
  color table above for the flagged ratio). Same border-radius as the input fields.
- **Email / password inputs** — same `type`, `autocomplete`, and paste/autofill rules as light.
  1px `hairline` (dark) border, `text-primary` (dark) value text, no placeholder-only labeling.

## Content

Identical to light: same wordmark, same h1 ("Sign in"), same support line ("Sign in to your
Atlas workspace."), same button label, same absence of a signup link. Dark mode is a palette
swap of the same content, not a rewrite.

## Bands / chrome

Same as light — desktop, no mobile bands, no sticky chrome to reserve on a pre-auth screen.

## Composition anchor & background mode

- **Anchor:** `centered-statement` — same as light, unchanged by palette.
- **Background mode:** `flat-surface` — same as light. One solid dark substrate, nothing else.

## Self-check (embarrassment gate)

Read back against `DIRECTION.md` §7's dark table: `text-primary`, `text-secondary`,
`accent-dark`, and `hairline` all trace directly. The one derived pairing (substrate-dark text on
accent-dark button fill) is explicitly flagged rather than silently presented as measured, same
discipline as the light file's button-fill flag. No glass anywhere, layout matches light exactly
(same numbers, different palette), one h1, label-above-field on both inputs, WCAG 3.3.8 respected
in the component notes. Would put my name on this.
