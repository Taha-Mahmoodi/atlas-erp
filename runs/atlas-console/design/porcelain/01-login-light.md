# porcelain — 01 Login — light — 1440×900

Anchor: **centered-statement** · Background: **flat-surface** (register §6 closed menus).
The run's only surface without the 248px shell. No sidebar, no glass, no floating layers.
Content source: `shots/current/login.png`, verbatim. h1 decision: **h1 = "Atlas ERP"**
(masthead); "Sign in to continue." is the sub line, not a heading.

## Region map (x, y, w, h — sums checked in §9)

| Region | x | y | w | h |
|---|---|---|---|---|
| Canvas (bg) | 0 | 0 | 1440 | 900 |
| Card | 520 | 247 | 400 | 406 |
| Masthead row (mark + h1) | 544 | 271 | 352 | 28 |
| Subtitle | 544 | 305 | 352 | 20 |
| Field group — Company | 544 | 349 | 352 | 60 |
| Field group — Email | 544 | 425 | 352 | 60 |
| Field group — Password | 544 | 501 | 352 | 60 |
| Sign in button | 544 | 585 | 352 | 44 |

Card is centered both axes: x = (1440−400)/2 = 520; y = (900−406)/2 = 247.
Card padding 24px all sides → inner width 352. Vertical rhythm: masthead 28 → gap 6 →
subtitle 20 → gap 24 → three 60px field groups with 16px gaps (212) → gap 24 → button 44.
Field group anatomy: label 14 (10.5px mono-caps, lh 14) → gap 6 → input 40.

## Per-region spec

- **bg**: `#f7f7f8`, edge to edge. Nothing else on it — no texture, no gradient.
- **Card**: card `#ffffff`, r14, 1px line `#e9e9ee` border, register shadow
  `0 1px 2px rgba(23,24,28,.04), 0 10px 28px -8px rgba(23,24,28,.09)`.
- **Masthead**: 26px workspace mark (r7, ink `#17181c` fill, white 12px/700 "A" — the §3
  switcher mark, no invented logo) + 10px gap + h1 "Atlas ERP" (§2 h1: Inter 22px/650,
  −0.01em, lh 28), ink. Mark vertically centered on the 28px row.
- **Subtitle**: "Sign in to continue." — §2 sub, 13px/450 lh 20, ink2 `#6b6d76`.
- **Field labels**: §2 mono-caps — JetBrains Mono 10.5px/600, .06em, uppercase, ink2.
  Rendered: COMPANY · EMAIL · PASSWORD. No asterisks: every field is required, `required`
  set on all three; requiredness is stated by validation, not decoration (§8).
- **Inputs**: 352×40, r10, 1px line border, card fill. Value text 13px/450 ink; placeholder
  13px/450 ink2 (Company: "acme" · Email: "you@company.com" · Password: none).
  `autocomplete`: organization / email / current-password. `type`: text / email / password.
  Paste and password managers never blocked; no CAPTCHA (register §5, WCAG 3.3.8).
- **Sign in button**: 352×44, r10, ink `#17181c` fill, "Sign in" 13px/550 white — the §3
  standalone-primary rule: not in a page head, so it renders 44px outright, full card width.
- **Focus ring**: 2px solid acc `#3f5bf6`, 2px offset, `:focus-visible` only.

## Content (verbatim from live app)

Atlas ERP · Sign in to continue. · COMPANY (placeholder "acme") · EMAIL (placeholder
"you@company.com") · PASSWORD · Sign in. **No links** — no forgot-password, no sign-up,
none added.

## States owed

**(a) Error — bad credentials.** One plain sentence inserted between subtitle and the
Company group: "That email or password didn't match. Nothing was locked." — 13px/450 lh 20,
bad-tx `#b23425` on card (§1 ratio **6.16**). Wraps to 2 lines at 352px → block h 40, with
16px below it; card grows to 462, recenters to y = 219; everything below shifts by +56.
`role="alert"` on the sentence. All input preserved — no field cleared, no field border
changes (the error is form-level, not per-field), focus moves to the alert container
(`tabindex="-1"`).

**(b) In-flight.** Button label → "Signing in…", `disabled`, cursor default, ink fill
held at full value (label change is the state, not a spinner — §3 skeleton rule kept in
spirit). Inputs stay enabled and editable; nothing else dims.

**(c) Validation — empty required field.** Per-field message under the offending input:
"Company is required." / "Email is required." / "Password is required." — 12px/450 lh 16,
bad-tx, margin-top 6 (group grows 60 → 82). Input gets `aria-invalid="true"` +
`aria-describedby` pointing at its message. Message removed the moment the field is
non-empty on next submit. Border stays line + message — the 1px line border is never the
sole signal (§1).

## Type table (deltas from §2 only)

| Use | Spec | Delta |
|---|---|---|
| h1, subtitle, mono-caps labels | per §2 | none |
| Input value / placeholder | Inter 13px/450 lh 20 | body role reused in a control |
| Button label | Inter 13px/550 | §3 ink-button spec |
| Error sentence | Inter 13px/450 lh 20, bad-tx | body role in bad-tx |
| Field validation message | Inter 12px/450 lh 16, bad-tx | pill size at 450, bad-tx |

## Palette citation (pairs used only — §1 verified ratios)

| Pair | Ratio |
|---|---|
| ink on card | 17.74 |
| ink2 on card (labels, placeholder, subtitle) | 5.15 |
| white on ink (button) | 17.74 |
| bad-tx on card (error + validation) | 6.16 |
| acc focus ring vs bg | 4.86 (floor 3.0) |
| acc vs card (ring on inputs/button) | 5.20 (floor 3.0) |
| line vs card | 1.21 — decorative only, never sole signal |

## Accessibility

One `h1` ("Atlas ERP"), one `main` (the card region). Skip link omitted: no repeated
blocks precede content on this surface (bypass-blocks not triggered); every other surface
in the run keeps it. Labels are visible `<label for>` elements, not placeholders-as-labels.
Autocomplete tokens as above (WCAG 1.3.5). Error/validation announced via `role="alert"` /
`aria-describedby`; no color-only signaling; no timeout, no CAPTCHA, paste allowed. Tab
order: Company → Email → Password → Sign in. 44px submit target; 40px inputs are full-width
(352px) — pointer target comfortably exceeds 24px minimum, and this is a form field, not a
row-action cluster.

## Self-check

Vertical: 271+28+6=305 ✓ · 305+20+24=349 ✓ · 349+60+16=425 ✓ · 425+60+16=501 ✓ ·
501+60+24=585 ✓ · 585+44+24=653 = 247+406 card bottom ✓. Horizontal: 520+24=544,
544+352+24=920 = 520+400 ✓. Inner sum 24+358+24=406 ✓. Error-state card 406+56=462,
(900−462)/2=219 ✓. All tokens and ratios read back against `_register.md` §1–§5; both
menu tokens are from §6's closed lists.
