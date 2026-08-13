# the yard: Surface 1 of 7 — Login

**Mode:** light · **Canvas:** 1440×900 (fixed coded viewport; screen is a centered composition
within it, not full-bleed) · **Composition anchor:** `centered-statement` · **Background mode:**
`flat-surface`

Pre-authentication. No bento lanes — nothing to show status for before auth, so this is the one
surface in the set with zero signal-tokens on it except a purely decorative brand-mark chip. The
calmest, most open screen in the seven; every other surface is dense, this one is one small block
floating on an open field.

## Layout — numbers

Base unit: 8px. Control floor: 44px.

- **Substrate:** fills the full 1440×900 canvas, `substrate` fill, no texture, no image — the
  content (card) is the only asset inline on it, hence `flat-surface`.
- **Card:** 400px wide, height auto (≈496px), centered both axes — `left: (1440-400)/2 = 520px`,
  `top: (900-496)/2 ≈ 202px`. `card` fill, `20px` border-radius, `1px solid hairline` border
  (decorative only — the actual boundary signal is the shadow below it, so the hairline is never
  the sole signal per its own palette note), two-layer soft shadow:
  `0 1px 2px oklch(0.21 0.015 290 / 6%), 0 24px 48px oklch(0.21 0.015 290 / 10%)`. No glass, no
  blur — flat opaque card per the concept's "no glass" rule.
- **Card padding:** 40px (5u) all sides → content column width 320px.
- **Vertical rhythm inside the card**, top to bottom:
  1. Brand-mark row, centered: 32×32px rounded-square token (`10px` radius — the concept's one
     atomic unit, here used purely decoratively since there's no status to show yet) filled
     `accent-tint`, glyph `accent-ink`, 8px gap, wordmark "Atlas" 15px/600 (lane-header size),
     `text-primary`.
  2. 24px (3u) gap → **h1** "Sign in" — 20px/600, `text-primary`, centered. The one h1 on the
     screen.
  3. 8px (1u) gap → subtext, one line, 14px/450, `text-secondary`, centered: "Sign in to your
     Atlas workspace."
  4. 32px (4u) gap → form starts.
  5. **Email field:** label "Email" (12px/450, `text-primary`, always visible, never
     placeholder-only) → 4px (0.5u) gap → input, full 320px width, 44px height, 12px
     border-radius, `1px solid hairline`, `card` background, 12px horizontal padding, value text
     14px/450. `type="email" autocomplete="email" autofocus`.
  6. 16px (2u) gap → **Password field:** label "Password" (12px/450) → 4px gap → input, same
     dimensions, `type="password" autocomplete="current-password"`. No `onpaste` blocking, no
     `autocomplete="off"`, no readonly trick — paste and password-manager autofill both work
     (WCAG 3.3.8). Inline show/hide toggle: 44×44px icon-button inset at the input's right edge,
     real `<button type="button" aria-label="Show password">`, sits inside the field's own 44px
     row so it costs no extra vertical space.
  7. 8px (1u) gap → utility row: "Forgot password?" link, right-aligned in the 320px column,
     12px/450, `accent-ink`.
  8. 24px (3u) gap → **primary CTA:** "Sign in" button, full 320px width, 44px height, 12px
     border-radius, solid fill `accent-emphasis` (not the gradient CTA token — label is 14px,
     under the gradient's 18px-bold-only floor, so solid fill is the only legal choice here),
     label white, 14px/600, centered. `type="submit"` — the form's native submit handles Enter in
     either field; no JS override.
- **Footer line**, outside the card, on the substrate: 24px below the card's bottom edge,
  centered, 12px/450, `text-secondary`: "New to Atlas? Contact your workspace admin."
- **Skip-to-content link:** first element in DOM/tab order, before the card. Visually hidden
  (1×1px clipped) until `:focus-visible`, then fixed at `top: 16px; left: 16px`, `accent-ink`
  background, white text, 14px/600, 8px 16px padding, 8px border-radius, above everything.
  Copy: "Skip to sign-in form" — targets the email input.
- **Focus ring** (skip link, both inputs, show/hide toggle, forgot-password link, sign-in
  button): `2px solid accent-ink`, `2px` offset, `:focus-visible` only, no default outline
  otherwise. `accent-ink` is `oklch(0.44 0.15 290)` — checked against both backgrounds it can sit
  on: against `card` (`oklch(1 0 0)`) it's the table's own ~7:1 pairing; against `substrate`
  (`oklch(0.985 0.004 290)`, L 0.985 vs `card`'s L 1 — effectively the same lightness) the ring
  reads at the same contrast. Holds on both.
- **No sticky chrome on this screen.** Pre-auth, no nav, nothing persistent to reserve — the
  four/desktop-band equivalent is N/A here by design, not by omission.

## Type

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| Wordmark | Inter Variable | 15px | 600 | 20px |
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / subtext / input value | Inter Variable | 14px | 450 | 20px |
| Field label / meta / footer | Inter Variable | 12px | 450 | 16px |
| Button label | Inter Variable | 14px | 600 | 20px |

No JetBrains Mono on this screen — there is no document identifier to render.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas | substrate | `oklch(0.985 0.004 290)` | text-primary | ~15:1 |
| Card fill | card | `oklch(1 0 0)` | text-primary | ~16:1 |
| Subtext, meta, labels | text-secondary | `oklch(0.46 0.02 290)` | on card | ~6.5:1 |
| Card border, decorative | hairline | `oklch(0.89 0.01 290)` | — sub-3:1, decorative only; boundary carried by the shadow, not this line |
| Links, focus ring | accent-ink | `oklch(0.44 0.15 290)` | white / on card | ~7:1 |
| Sign-in button fill | accent-emphasis | `oklch(0.53 0.18 290)` | white (button label) | ~4.8:1 — estimated, not script-verified (source RISK 4); do not drop the label below 14px |
| Brand-mark chip fill | accent-tint | `oklch(0.94 0.035 290)` | accent-ink (glyph) | ~6:1 |

## Content direction

Two fields, one action, one line of human copy each — real placeholder-length strings only
("Sign in to your Atlas workspace.", "Forgot password?", "New to Atlas? Contact your workspace
admin."), no invented brand claims, no lorem, no fabricated numbers; "Atlas" is the product's real
name, no invented logo drawn — the brand mark is the token-shape itself.
