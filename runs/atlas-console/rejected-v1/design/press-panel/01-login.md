# press-panel: Surface 1 of 7 — Login

Coded-comp mode. Canvas: **1440 × 900 fixed viewport**, desktop, full chrome. Platform mode: N/A.

Composition anchor: **`centered-statement`**
Background mode: **`flat-surface`**

One line: login is one 400px form block on the vertical and horizontal axis of an otherwise empty steel field — nothing subordinate competes with it, which is the calmest reading in the set; surfaces 2–7 run `dense-grid` (worklist, item table) or `left-rail-caption`/`right-rail-caption` (nav rail + detail), so this is the only surface in the set with no rail, no table, and no secondary field at all.

---

## Layout move, with numbers

```
0,0 ─────────────────────────────────────────────── 1440,0
│ STICKY HEADER — 0,0 to 1440,48 (48px, reserved)   │
│   1px hairline border-bottom, oklch(0.86 0.005 58) │
│   "Atlas" wordmark, 16px inset left, 14px/600      │
│   No nav rail, no ⌘K here — both require a session │
├─────────────────────────────────────────────────── ┤
│                                                     │
│         CONTENT — 0,48 to 1440,900 (852px)         │
│                                                     │
│              ┌─────────────────────┐               │
│              │  form block         │               │
│              │  400px wide         │               │
│              │  x: 520–920         │               │
│              │  y: 294–654 (≈360h) │               │
│              │  centered-statement │               │
│              └─────────────────────┘               │
│                                                     │
└─────────────────────────────────────────────────── ┘
```

**Form block, top to bottom** (400px wide, no card border, no shadow — flat on substrate):

| Element | Spec | Vertical rhythm |
|---|---|---|
| Tenant lockup | "Northwind Trading Co." — title role | line-height 28px, margin-bottom 8px |
| Subline | "Sign in to your workspace" — body role, secondary text | line-height 20px, margin-bottom 32px |
| Email label | "Email" — meta role | line-height 16px, margin-bottom 6px |
| Email input | 400×**40px** (control-height floor), radius 8px, 1px hairline border, 12px horizontal padding, value in body role | margin-bottom 16px |
| Password label | "Password" — meta role | line-height 16px, margin-bottom 6px |
| Password input | 400×40px, same spec as email; plain-text "Show" toggle, meta role, right-inset 12px — no invented eye-glyph icon | margin-bottom 12px |
| *(error state only)* | "— Incorrect email or password." — body role, secondary text color (not a new hue — see Restraint note below); both input borders switch from hairline `oklch(0.86 0.005 58)` to `oklch(0.44 0.008 58)` 1px | margin 8px top / 12px bottom |
| Forgot-password link | right-aligned, meta role, accent-ink color (interactive text) | line-height 16px, margin-bottom 24px |
| **Clay button — "Sign in"** | **400×48px**, radius **18px** (16–20px range), embossed — see shadow spec below | margin-bottom 16px |
| Footnote | "Trouble signing in? Contact your workspace admin." — meta role, secondary text, centered | line-height 16px |

Block height ≈360px (no-error) / ≈394px (error state) inside an 852px content area → vertically centered, top edge at y=294 (no-error case).

### Clay button — the one dimensional object on the panel

- Size: 400 × 48px, radius 18px
- Fill: `accent-emphasis` `oklch(0.60 0.14 58)`
- Label: "Sign in", clay-button role, white (`oklch(1 0 0)`), centered
- Shadow pair, **light source fixed top-left**, never inverted between light/dark:
  - Highlight: `-6px -6px 12px oklch(1 0 0 / 0.65)` (top-left, lighter than surface)
  - Cast shadow: `6px 6px 16px oklch(0.55 0.03 58 / 0.35)` (bottom-right, darker than surface)
- `:focus-visible`: **2px solid `oklch(0.40 0.10 58)` (accent-ink) ring, 2px offset** — not a deeper shadow. This is the required accessibility fix for the claymorphism role.
- This is legal placement #1 of the two system-wide clay roles (primary/confirming CTA). Placement #2 (pending/in-progress status pill) does not appear on this surface — nothing on a login screen is "pending."

**Restraint check for this surface**: no cards, no shadows anywhere on the panel except the one button above. The email/password inputs are flat hairline-bordered fields, not clay. The error state does not clay or color-code — it darkens the existing border ramp one step and states the fact in body type. Nav rail is absent entirely (not "flattened," genuinely not present) because there is no session yet to navigate within — it begins at surface 2 (role-home).

---

## Type table

| Role | Face | Size | Weight | Line-height | Numeric |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 28px | — |
| Body / data | Inter Variable | 14px | 450 | 20px | tabular-nums on numeric cols only (none on this surface) |
| Meta | Inter Variable | 12px | 450 | 16px | — |
| Clay-button label | Inter Variable | 15px | 600 | 20px | — |

One face, system-wide, per direction: a flat panel with one dimensional button is a material distinction, not a typographic one.

---

## Paired colors, with ratios

Fresh contrast math run against the OKLCH values in this dispatch (OKLab→linear-sRGB→WCAG relative luminance), **all marked computed, not rendered** — verify against the actual browser render before ship.

| Pair | Computed ratio | Note |
|---|---|---|
| primary text `oklch(0.19 0.006 58)` on substrate `oklch(0.98 0.002 58)` | **17.44:1** (computed) | field values, form labels' parent text |
| secondary text `oklch(0.44 0.008 58)` on substrate | **7.34:1** (computed) | meta labels, subline, footnote, error copy |
| accent-ink `oklch(0.40 0.10 58)` on substrate | **8.97:1** (computed) | forgot-password link. Dispatch cites a verified ≈8.71:1 pair elsewhere in this run — this run's own fresh math lands close (8.97 vs 8.71), within expected drift for independent computation. **Flag:** this OKLCH value is slightly outside the sRGB gamut (linear blue channel goes negative before gamma correction) — a standards-compliant browser gamut-maps it via CSS Color 4, so the rendered hue will be marginally less saturated than raw OKLCH math implies. Approx clipped hex ≈ `#6E3700`. |
| white `oklch(1 0 0)` on accent-emphasis `oklch(0.60 0.14 58)` | **4.12:1** (computed) | **clay button label. Dispatch cites a verified 5.06:1 at similar L/C and says "expect close" — 4.12:1 is not close, and it fails WCAG AA (4.5:1) for the 15px/600 label, which is below the 18.66px-bold large-text threshold that would drop the requirement to 3:1.** This is the one CTA on the calmest surface in the set; flagging rather than silently patching, since accent-emphasis is a system-wide token, not local to this surface — see "Anything unsatisfied" below. |
| primary text on accent-tint `oklch(0.93 0.035 58)` | 14.94:1 (computed) | not used on this surface; carried for reference against sibling surfaces |
| hairline border `oklch(0.86 0.005 58)` on substrate | 1.45:1 (computed, non-text) | UI-component-level, not text — this is a hairline divider/input border, correctly subtle, not held to the 3:1 text-adjacent-graphic floor since it's a low-emphasis rest-state border, not a required-visible control boundary |

---

## Content direction

One line: real HTML `input type="email"` / `type="password"` with `autocomplete="email"` / `autocomplete="current-password"`, no paste-blocking, no autofill interception — the tenant name is the one piece of real-feeling content on the screen and the error message is a single flat sentence, not a red banner.

---

## Embarrassment-gate self-check

- Hexes: computed approximations traced back to the dispatched OKLCH values above; accent-ink's out-of-gamut clip is called out rather than papered over.
- Body-size type (14px) at 7.34:1–17.44:1 on substrate — well clear of 4.5:1.
- Sticky header (48px) reserved, not painted over; desktop chrome-equivalent to the mobile four-band rule.
- Collision readable: exactly one embossed object on an otherwise flat, bordered, hairline panel — the operator's hand has one thing to reach for.
- Composition (`centered-statement` / `flat-surface`) differs from the dense-grid/rail surfaces this set's siblings will run.
- No garbled text, no invented logo, no fabricated numbers, no lorem — tenant name and copy are plausible-length placeholders in Atlas's actual domain (workspace login), not marketing filler.
- Would a designer sign this: **yes, with one open item carried forward** — the clay-button contrast number below is a real finding, not a rendering slip, and it is surfaced rather than shipped quietly.

---

## Return

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/press-panel/01-login.md`
- **Composition anchor:** `centered-statement`
- **Background mode:** `flat-surface`
- **One line:** a single 400px form block on-axis in an empty steel field, with exactly one embossed object (the "Sign in" button) as the only dimensional thing on the panel — the calmest, least-composed surface in the set, deliberately contrasting the dense-grid/rail surfaces that follow it.
- **Anything unsatisfied:**
  1. White-on-accent-emphasis computes to **4.12:1**, not the ≈5.06:1 the dispatch expected, and fails WCAG AA for the 15px/600 button label (needs 4.5:1; not large enough for the 3:1 exception). This is a system-wide token (used wherever the clay CTA role appears), not fixable locally on this one surface — needs a design-lead call: darken `accent-emphasis`, or bump the label past the large-text threshold, or accept and document the AA gap.
  2. `accent-ink` at `oklch(0.40 0.10 58)` is fractionally outside the sRGB gamut; CSS Color 4 gamut-mapping will render it slightly less saturated than raw OKLCH math shows. Flagged, not corrected — a rendering-engine question, not a spec error.
  3. No danger/error color token exists in the dispatched palette. Rather than invent an off-system hue, the error state stays inside the given neutral ramp (secondary-text color, darkened input borders) — consistent with "error states are never clayed... quiet and plain," but worth confirming this reading is what was intended versus a semantic red being expected elsewhere in the system.
