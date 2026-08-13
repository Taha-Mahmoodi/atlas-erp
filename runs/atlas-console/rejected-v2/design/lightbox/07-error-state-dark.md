# lightbox: Surface 7 of 7 — Error State (Record Not Found) — dark

**Job:** identical to the light spec — replace the confirmed-defective blank "Edit item" form
with one honest, announced sentence and a real way back, on a non-existent/malformed record ID.
Layout, structure, and copy are identical to the light file; only the palette and the resulting
foreground/background pairings change — "one design in two palettes," same framing the opaque
layer uses everywhere else in this concept.

**Canvas:** 1440×900, fixed, web/desktop-only. Same as light. **Composition anchor:**
`centered-statement` · **Background mode:** `flat-surface` — both unchanged by palette.

## Layout — numbers

Identical geometry to the light spec, not re-derived here: rail `x:0–240,y:0–900`; glass bar
`top:16,left:16,right:16 → 1408×56, 18px radius`; content region `x:240–1440,y:88–900`; message
block centered at `x:840,y:494`, spanning `y:450–538` (h1 `450–478`, 16px gap, link hit-zone
`494–538`). Only the fill values below change.

- Substrate fill (canvas, rail, content): `oklch(0.155 0.01 290)`.
- Rail active-row fill: `row-alt` `oklch(0.205 0.012 290)`.
- Rail border, decorative: `hairline` `oklch(0.33 0.014 290)`.
- Glass command bar (dark art direction — less opaque, less blurred border, reads through more,
  per §7's explicit "dark mode runs less opaque" rule): fill `color-mix(in oklab,
  oklch(0.22 0.015 290) 50%, transparent)`, `backdrop-filter: blur(20px)`, border `color-mix(in
  oklab, white 25%, oklch(0.3 0.02 290) 75%)`.
- **h1 error message** — same markup, same `role="alert" aria-live="assertive" aria-atomic="true"
  tabindex="-1" id="main-content"`, same programmatic focus-on-route-entry, same suppressed
  `:focus` outline (non-interactive element) — only the text color changes: `oklch(0.62 0.15 25)`.
  Same `display:inline-block; white-space:nowrap` pin to guarantee one line.
- **"Back to items" link** — same component, same copy, same real 44px block target, same
  target-size reasoning as light (standalone line, not inline in a sentence — no WCAG 2.5.8
  exception applies) — color `accent-dark oklch(0.77 0.13 290)`.
- **Skip link** — same behavior and position, `accent-dark` background, dark substrate-colored
  text (light-fill/dark-text, matching the button convention already set on surface 01's dark
  spec for this palette's one saturated chip), same copy "Skip to error message" targeting
  `#main-content`.

## Type

Identical faces, sizes, weights, line-heights to the light spec — only color changes:

| Role | Face | Size | Weight | Line-height | Color |
|---|---|---|---|---|---|
| Wordmark (bar) | Inter Variable | 15px | 600 | 20px | `text-primary` (dark) |
| h1 (title) — error message | Inter Variable | 20px | 600 | 28px | error-text (dark) |
| Body — "Back to items" link | Inter Variable | 14px | 450 | 20px | `accent-dark` |
| Command-bar label | Inter Variable | 14px | 500 | 20px | `text-primary` (dark), on scrim |
| Rail nav label | Inter Variable | 14px | 500 | 20px | `text-primary` (dark) |

`meta` unused, same as light. No JetBrains Mono, same reason as light.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas, rail, content | substrate | `oklch(0.155 0.01 290)` | text-primary (dark) | ~15:1 |
| Rail active-row fill | row-alt | `oklch(0.205 0.012 290)` | text-primary (dark) | ~13:1 |
| Rail border | hairline | `oklch(0.33 0.014 290)` | — decorative only |
| **Error message text** | error-text (dark) | `oklch(0.62 0.15 25)` | on substrate `oklch(0.155 0.01 290)` | **~5.0:1** — computed via OKLCH→sRGB (Ottosson matrices), same method and same caveat as the light file: not tabulated in `DIRECTION.md` §7, worker-derived, flagged for build-time re-verification. Clears 4.5:1 at 20px with a smaller margin than light (5.0 vs 6.3) — worth re-checking first if any script-based re-measurement finds drift. |
| "Back to items" link, focus ring, skip-link bg | accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 (per `DIRECTION.md` §7's dark table) |
| Glass command bar fill | glass panel (dark) | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `blur(20px)` | text via inner scrim | flagged for build-time re-measurement (RISK 1), same as every other surface carrying this bar |

## Content direction

Identical to light: same message, same link copy, same terminology-locked "items," no invented
data, no raw backend string, no lorem. Dark mode is a palette swap of the same content and the
same accessibility contract, not a rewrite.

## Self-check (embarrassment gate)

All dark values trace to `DIRECTION.md` §7's dark table where a table entry exists (substrate,
row-alt, hairline, accent-dark, glass panel); the one new pairing (error-text on substrate) is
computed and explicitly flagged, same discipline as the light file. Ratio margin on the error
message is thinner in dark (~5.0:1) than light (~6.3:1) — noted rather than smoothed over. Layout,
focus behavior, `role="alert"`, skip link, and the "no card/no icon" rule all match light exactly.
Would put my name on this.
