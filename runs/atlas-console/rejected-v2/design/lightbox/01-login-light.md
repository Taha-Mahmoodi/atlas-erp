# lightbox: Surface 1 of 7 — Login (light)

**Job:** let a known user get from "not authenticated" to "inside their Atlas workspace" in the
fewest possible moves, with zero visual noise to burn attention on before they're even in.

**Concept restraint, applied literally to this screen:** the glass command bar does not exist
pre-auth — there is nothing to search or jump to before there's a session. So this surface has
**no glass anywhere**. It is the plainest possible instance of the concept's opaque data layer:
one flat substrate, one centered block of type and controls, no card, no shadow, no border
around the form. Hierarchy is type size/weight and whitespace only, exactly as the collision
sentence requires of every non-glass surface.

**Canvas:** 1440×900, fixed, web/desktop-only. No responsive breakpoints specified at this
attempt — flagged if a narrower viewport is needed later.

---

## Layout — numbers

Single flat substrate fill, full canvas, `oklch(0.99 0.003 290)`. No left rail, no top bar, no
footer — nothing else exists on this screen besides the skip link and the centered form column.

**Skip-to-content link** — first element in DOM/tab order, visually hidden (`position:
absolute; clip`) until `:focus-visible`, then renders top-left at `x:16 y:16`, `padding: 8px
12px`, body scale 14px/450, `text-primary` on `substrate`, 1px `hairline` border. Targets the
`<main>` wrapping the form.

**Content column** — width `360px`, horizontally centered: left edge `x = 540px`
(`(1440 − 360) / 2`), right edge `x = 900px`. Vertically centered as a block: computed content
height ≈ `380px`, so block top `y ≈ 260px` (`(900 − 380) / 2`), block bottom `y ≈ 640px`. No
outer container, no padding box, no background change behind the column — it sits directly on
the substrate.

Vertical stack inside the column, top to bottom, 8px base unit:

| # | Element | Height | Margin-bottom | Notes |
|---|---|---|---|---|
| 1 | Wordmark "Atlas" | 24px | 32px (4×8) | `text-primary`, meta scale weight, `aria-hidden` decorative mark — not a heading, does not compete with the h1 |
| 2 | `<h1>` "Sign in" | 28px line-height | 8px | title scale, the **only** h1 on the screen |
| 3 | Support line | 20px line-height | 32px (4×8) | `text-secondary`, body scale, one sentence: see Content, below |
| 4 | `<label>` "Email" | 16px line-height | 4px | meta scale, `text-secondary`, sits directly above its field |
| 5 | Email input | 44px | 16px (2×8) | full column width (360px), see Component notes |
| 6 | `<label>` "Password" | 16px line-height | 4px | meta scale, `text-secondary` |
| 7 | Password input | 44px | 8px | full column width, see Component notes |
| 8 | "Forgot password?" link | 16px line-height | 24px (3×8) | meta scale, right-aligned within the column, `accent-ink` |
| 9 | Primary CTA "Sign in" | 44px | — | full column width, see Component notes |

Sum of the stack ≈ 380px, matching the vertical-centering math above. No footer row, no "create
an account" link — Atlas ERP is admin-provisioned per-tenant, not self-serve, so a signup
affordance would be inventing a flow that doesn't exist on this product. That is a content
decision, not an omission.

---

## Type table

| Role | Face | Size | Weight | Line-height | Color |
|---|---|---|---|---|---|
| Wordmark | Inter Variable | 14px | 600 | 24px | `text-primary` |
| h1 (title) | Inter Variable | 20px | 600 | 28px | `text-primary` |
| Support line (body) | Inter Variable | 14px | 450 | 20px | `text-secondary` |
| Field label (meta) | Inter Variable | 12px | 450 | 16px | `text-secondary` |
| Field value (body) | Inter Variable | 14px | 450 | 20px | `text-primary` |
| "Forgot password?" (meta) | Inter Variable | 12px | 450 | 16px | `accent-ink` |
| Button label (body) | Inter Variable | 14px | 600 | 20px | white |

One face, whole screen, per the concept's stated reason: a second face would compete with the
opaque/glass distinction, and this screen doesn't even have the glass half to distinguish from.

---

## Color pairs — measured/estimated (per §11 disclosure)

| Pair | Foreground | Background | Ratio | Used for |
|---|---|---|---|---|
| text-primary / substrate | `oklch(0.20 0.012 290)` | `oklch(0.99 0.003 290)` | ~16:1 | h1, field values, wordmark |
| text-secondary / substrate | `oklch(0.47 0.015 290)` | `oklch(0.99 0.003 290)` | ~6.3:1 | support line, field labels |
| accent-ink / substrate | `oklch(0.43 0.15 290)` | `oklch(0.99 0.003 290)` | ~7.2:1 | "Forgot password?" link, focus ring |
| white / accent-ink (button fill) | white | `oklch(0.43 0.15 290)` | ~7.2:1 by symmetry with the accent-ink/white pairing already stated in `DIRECTION.md` §7 — not independently re-derived, flagged per §11 | Primary CTA fill + label |
| hairline | `oklch(0.90 0.008 290)` | — decorative-only | n/a | input borders, skip-link border |

`accent-emphasis` (~4.9:1, unverified, flagged "don't use under 14px" in the brief) is **not
used anywhere on this screen** — the button is 14px exactly at that floor, so it takes the
verified `accent-ink` pairing instead rather than sitting on the edge of an unverified ratio on
the one interactive control that matters most on this screen.

---

## Component notes

- **Email input** — `type="email"`, `autocomplete="username email"`, `id="email"`, labelled by
  `<label for="email">`. 44px height (control floor), full 360px width, 1px `hairline` border,
  `12px` horizontal padding, body scale value text. No placeholder text — the label is the only
  affordance, per the access brief's "label above field always, never placeholder-only."
- **Password input** — `type="password"`, `autocomplete="current-password"`, `id="password"`.
  Same 44px/360px/border/padding as email. Show/hide toggle: icon button, 24×24 icon inside a
  44×44 hit target, right-aligned inside the field, `aria-label="Show password"` /
  `"Hide password"`, toggles `type` between `password`/`text`. **No `onpaste` handler, no
  `autocomplete="off"`, no JS blocking paste or IME input** — WCAG 3.3.8 compliance is a
  negative requirement (don't add the blocking code), not a positive one to build.
- **Primary CTA "Sign in"** — `<button type="submit">`, 44px height, full 360px width,
  `accent-ink` fill, white label, `border-radius` matched to the input fields (kept identical
  across the two so the button doesn't read as a separate material — still flat, still opaque).
  Native `<form onSubmit>` — Enter in either field submits, no keyboard handler needed beyond
  what the form element gives for free.
- **Focus ring** — `2px solid accent-ink`, `2px offset`, `:focus-visible` only (not on
  mouse-click focus), applied to both inputs, the show/hide toggle, "Forgot password?", the
  submit button, and the skip link.
- **Errors** (inline validation, not this screen's dedicated error surface) — if shown, render
  below the relevant field, 12px meta scale, using the triangle glyph from the concept's status
  vocabulary (never color alone) paired with `oklch(0.43 0.02 25)`-family error text — carried
  forward from the concept's error grammar, not fully specified here since surface 07 owns it.

## Content

- Support line: **"Sign in to your Atlas workspace."** — real product name, no invented brand,
  no superlative, states exactly what the screen does.
- Button label: **"Sign in"** — same string as the h1's verb, deliberately plain, no "Get
  started" filler.
- No lorem, no placeholder rows, no fabricated numbers — the whole screen is five short real
  strings (wordmark, h1, support line, two labels, one link, one button).

## Bands / chrome

Desktop, not mobile — the four mobile safe-area bands don't apply. There is no sticky chrome on
this screen to reserve space for (no header, no left rail — those only exist post-auth), so
nothing is reserved because nothing persists past this screen.

## Composition anchor & background mode

- **Anchor:** `centered-statement` — the 360px form column sits on-axis, everything (wordmark,
  copy, fields, CTA) subordinate to that one centered block, nothing competing for a second
  focal point.
- **Background mode:** `flat-surface` — one solid substrate fill, the form column inline on it,
  no texture, no gradient, no image. This is the mode the collision requires of every non-glass
  surface, and this screen has no glass object to contrast it against.

## Self-check (embarrassment gate)

Read back against the palette table above: all five color pairs trace to a row in `DIRECTION.md`
§7's light table or are explicitly derived-and-flagged (the white-on-accent-ink button fill).
`accent-emphasis` correctly excluded given its own "don't use under 14px" caveat. No glass
anywhere — confirmed against the concept's own rule that it doesn't exist pre-auth. One h1.
Label-above-field on both inputs. Focus ring and paste/autofill behavior both stated as
requirements a builder can implement without re-deriving them. Would put my name on this.
