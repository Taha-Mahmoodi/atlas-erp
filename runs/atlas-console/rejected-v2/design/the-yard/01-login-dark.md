# the yard: Surface 1 of 7 — Login

**Mode:** dark · **Canvas:** 1440×900 (fixed coded viewport; screen is a centered composition
within it, not full-bleed) · **Composition anchor:** `centered-statement` · **Background mode:**
`flat-surface`

Same design, retuned lightness/chroma only — layout, spacing, and structure are identical to the
light file. See `01-login-light.md` for the full layout rationale; this file states only what
changes: color, and the two pairings the source palette table doesn't hand over pre-made.

## Layout — numbers

Unchanged from light: 8px base unit, 44px control floor, 400px card centered at
`left: 520px, top: ≈202px`, `20px` card radius, `40px` card padding, identical vertical rhythm
(brand-mark row → h1 → subtext → 32px gap → email field → 16px gap → password field → 8px gap →
forgot-password link → 24px gap → CTA → footer line below card), identical skip-link mechanics
and identical focus-ring mechanics (`2px` solid, `2px` offset, `:focus-visible` only). Only the
fill/border/text colors below change. No sticky chrome on this screen in either mode.

## Type

Identical to light — same faces, sizes, weights, line-heights (Inter Variable throughout, no
JetBrains Mono on this screen).

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas | substrate | `oklch(0.19 0.012 290)` | text-primary | ~14:1 |
| Card fill | card | `oklch(0.24 0.012 290)` | text-primary | ~13:1 |
| Subtext, meta, labels | text-secondary | `oklch(0.68 0.015 290)` | on card | ~6:1 |
| Card border, decorative | hairline | `oklch(0.34 0.015 290)` | — same caveat as light: decorative only, boundary carried by the shadow |
| Links, focus ring | accent-dark | `oklch(0.76 0.14 290)` | on substrate / on card | ~6:1 |
| Brand-mark chip fill | accent-tint-dark | `oklch(0.30 0.05 290)` | accent-dark (glyph) | ~5:1 |
| Skip-link chip | accent-tint-dark bg | `oklch(0.30 0.05 290)` | accent-dark text | ~5:1 |

**Two pairings not handed over by the source table — derived here, flagged, not script-verified:**

1. **Sign-in button fill.** The dark palette in `DIRECTION.md` §6 defines no emphasis-fill
   equivalent to light mode's `accent-emphasis` (a saturated solid meant to carry a white label).
   `accent-dark` (`oklch(0.76 0.14 290)`) is the brightest, most saturated token the dark palette
   offers, so it's the functional analogue — used here as the button fill with a dark foreground
   (`oklch(0.16 0.02 290)`, near-black ink, not a table token) rather than white, since white
   text on an L 0.76 fill would fail contrast outright. The L-delta (0.76 → 0.16, ≈0.6) reads
   comfortably clear of 4.5:1 by estimation, but this pairing is **not** in the source table and
   should get the same script-verification pass flagged as RISK 4 for light mode's
   `accent-emphasis`, at Loop 2.
2. **Skip-link chip.** Built from the one verified reversible pairing available —
   `accent-tint-dark` / `accent-dark`, ~5:1 per the source table — rather than inventing a third
   color, unlike the button fill above which had no such pairing to reuse.

## Content direction

Identical copy to light mode: "Sign in to your Atlas workspace.", "Forgot password?", "New to
Atlas? Contact your workspace admin." — no new strings introduced for dark, no invented brand
claims, no lorem.
