chart-table: Surface 1 of 7 — Login
====================================

**Canvas:** 1440×900 fixed desktop viewport. Full chrome. No image generated (coded-comp mode).
**Composition anchor:** `centered-statement`
**Background mode:** `flat-surface`
**Anchor/bg one-line:** One card on the axis, nothing else competing for the eye — the calmest
possible statement of the system, rendered on a single solid substrate, before the day's forty
things exist yet. Role-home (surface 2) is where `dense-grid` and the plotted-fix markers take
over; this screen is deliberately the system in its dormant state, one flat plane with the grid
present but almost entirely unpopulated.

---

## 1. Layout move — exact numbers

Shared master grid (stated once here, mostly idle on this surface): 1440px canvas, 12 columns,
24px gutter, 80px fixed outer margins → `grid-template-columns: 80px repeat(12, 1fr) 80px;
column-gap: 24px`. Computed column width at this exact canvas width = (1440 − 160 − 264) / 12 =
**84.67px** (computed, not rendered — a CSS `1fr` track resolves this at runtime, no manual
rounding needed in implementation).

Two rows only:

- **Row 1 — header band, 48px exactly**, full-bleed width, `position: sticky; top: 0`, reserved
  per the run's sticky-header requirement. Holds only the running-head-as-breadcrumb, Source
  Serif 4 italic 13px, left-aligned at the 80px margin, reading `Atlas ERP` (no deeper
  breadcrumb path exists pre-auth — there is nowhere in the tree to be yet). Right side of the
  band is empty and **held**, not removed: it is where the persistent ⌘K search will dock once
  the authenticated shell mounts, so the header's height and horizontal rhythm do not shift at
  the moment of sign-in. No search box, no left rail on this surface — both are shell chrome
  that only exists after the role branch.
- **Row 2 — content, 852px** (900 − 48). `display: grid; place-items: center` inside the 12-col
  well; the card ignores the literal column edges (see below) because at rest, with zero rows of
  data, the grid has nothing to divide — that absence is the point.

**Card:** fixed 400px wide (not fluid — a login card doesn't reflow). This is 11px narrower than
the literal 4-column span (cols 5–8 = 4×84.67 + 3×24 = 410.68px) — logged openly as the one place
this surface breaks its own grid discipline, in service of a clean 400 over a grid-literal
410.68. Padding **40px** on all four sides (ties to the control-height floor below, giving the
card a single repeating unit). Internal content width = 320px.

Card contents, top to bottom, 320px column:

| Element | Height | Gap after |
|---|---|---|
| Brand row: dormant status-ring glyph (16px dia., 1.5px stroke) + "Atlas ERP" wordmark | 28px | 8px |
| Subhead "Sign in to continue." | 20px | 32px |
| Field: Company (label + 40px input) | 60px | 20px |
| Field: Email (label + 40px input) | 60px | 20px |
| Field: Password (label + 40px input) | 60px | 32px |
| Button: Sign in (full-width, 40px) | 40px | — |

**Every interactive control on this surface — both text inputs, the password input, and the
submit button — holds the 40px control-height floor exactly**, no exceptions. Card height in the
default state = 40 (pad-top) + 28 + 8 + 20 + 32 + 60 + 20 + 60 + 20 + 60 + 32 + 40 + 40 (pad-bot)
= **460px**.

Card vertical position: true center of the 852px content row = (852−460)/2 = 196px from row top.
Applied with a 24px optical-center nudge upward (standard for a form whose visual weight sits low
in the button) → **card top = 172px from row top / 220px from canvas top.**

**Error state** (invalid-credentials) inserts one inline banner between the Password field and
the button: heavy ring icon (14px dia., 2.5px stroke, error red) + one line of plain text, on an
error-tint fill, 8px/12px padding, 4px radius, full 320px width, height 36px. It replaces the 32px
gap before the button with 16px + 36px + 16px (net +36px). **Card height in the error state =
496px.** No serif is used in the banner — see content direction below.

Inputs, button, and the error banner all use **4px corner radius** (not specified in the
dispatch palette; chosen once here for the instrument-precise register the collision asks for —
sharper than a typical soft SaaS 8–12px radius, and reused as this run's standard control
radius unless a later surface overrides it).

---

## 2. Type table

| Role | Face | Size | Weight | Line-height | Used here |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 28px | "Atlas ERP" wordmark |
| Running-head / margin serif | Source Serif 4 Variable, italic | 13px | 400 | 18px | header breadcrumb only |
| Body / data | Inter Variable | 14px | 450 | 20px | field values, button label (600 on the label specifically), error banner text |
| Meta | Inter Variable | 12px | 450 | 16px | field labels, subhead uses 14px/450/20px (body scale, not meta — it is a sentence, not a label) |

Tabular-nums: not applicable on this surface — no numeric columns to align. Reserved for
list/detail surfaces (2–4).

---

## 3. Paired colors, with ratios

All ratios below are **computed, not rendered** — this run is coded-comp mode, so every number
here is a fresh OKLCH→linear-sRGB→WCAG relative-luminance calculation run against the exact
triplets in the dispatch, not an eyeballed estimate.

| Pair | OKLCH | Ratio | Verdict |
|---|---|---|---|
| primary text `oklch(0.22 0.008 58)` on substrate `oklch(0.99 0.002 58)` | — | **16.84:1** | clears AAA |
| secondary text `oklch(0.46 0.01 58)` on substrate | — | **6.94:1** | clears AA, short of AAA |
| accent-ink `oklch(0.40 0.07 58)` on substrate (dormant ring glyph stroke) | — | **9.14:1** | clears the dispatch's ≥7:1 expectation; close to but not identical to the "≈8.71:1 verified pair elsewhere" — that pair used a different exact triplet in-family, this is this surface's own fresh computation against the exact login-surface values |
| white on accent-emphasis `oklch(0.58 0.10 58)` (would-be button fill) | — | **4.41:1** | **fails the dispatch's own ≥4.5:1 expectation, marginally** — see flag below |
| accent-emphasis on substrate (text use) | — | **4.29:1** | also marginal for normal-size text |
| white on accent-ink (alternate fill, computed for comparison only) | — | **9.41:1** | comfortably clears — not used, see flag |
| error-text `oklch(0.44 0.16 25)` on substrate | — | **8.20:1** | clears AAA |
| error-text on error-tint `oklch(0.96 0.03 25)` | — | **7.34:1** | clears AAA |
| hairline border `oklch(0.90 0.006 58)` on substrate | — | **1.31:1** | see flag below — this is a decorative-line ratio, not a text ratio |

**Flag 1 — button fill contrast.** The dispatch names `accent-emphasis` as the fill and expects
white text to clear 4.5:1 on it; the computed ratio is 4.41:1, marginally under. The button
label is 14px/600 (18.66px bold is WCAG's large-text floor; 14px doesn't reach it), so this is a
real, if small, AA miss — not a rounding artifact. I have **not** substituted `accent-ink`
(9.41:1, computed above) as the fill, because `accent-emphasis` reads as the palette's intended
CTA color by name and swapping it changes a system-level decision I don't own. Flagging for Loop
1 rather than silently fixing it.

**Flag 2 — hairline as an input border.** 1.31:1 against substrate is fine for a decorative rule
between sections, but WCAG 1.4.11 asks for ≥3:1 on a UI component boundary that is the only
signal of a field's edge. On this surface every text input relies on the hairline alone to mark
its boundary. Not fixed here (it's a palette-level color, not mine to redefine) — flagged for
Loop 1 to confirm whether inputs get a secondary affordance (fill, shadow) or the hairline value
is reconsidered for form controls specifically.

Green/blue-gray/red hues for the plotted-fix ring family are given by the dispatch as hue angles
only (`H≈145°`, `H≈240°`, `H≈25°`), not full OKLCH triplets. This surface uses exactly one ring
(the dormant "confirmed" glyph in the brand row) and estimates it at `oklch(0.62 0.14 145)` —
same L/C family as accent-emphasis, hue swapped — flagged as an estimate for Loop 1 to confirm
before the ring family is built out on surfaces 2–4, where all five ring states appear.

---

## 4. Content direction

Real field labels and placeholders, matched against the current live app (`localhost:5173`
login) rather than invented: **Company** (placeholder `acme`), **Email** (placeholder
`you@company.com`), **Password**, button **Sign in**. Error copy is one plain sentence — "Company,
email, or password is incorrect." — worded as a person would say it, not a code.

**The restraint is explicit and load-bearing**: this is the one surface in the set where the
chart-metaphor is almost entirely switched off. There is nothing yet to plot — no tasks, no
due dates, no cluster to annotate — so the marginalia serif appears exactly once, in the header
breadcrumb, and is deliberately withheld from the error state even though a margin note would
be easy to justify there ("your password doesn't match the last three attempts" is exactly the
kind of judgment-call prose the serif exists for). The error state stays in plain Inter on
purpose: judgment commentary is for patterns across real data, not for a single failed login,
and reaching for the serif here would cheapen the one place later in the set where it's earning
its keep. The single dormant status ring in the brand row is the only place the system's real
visual language shows through — quiet, unlabeled, not yet doing work.

---

## 5. Embarrassment-gate self-check

- Hexes/ratios: recomputed from the exact OKLCH triplets via script, not eyeballed — caught two
  real marginal-contrast findings (button fill, hairline-as-border) rather than asserting the
  dispatch's stated expectations held without checking. Logged both rather than silently
  patching or silently ignoring.
- Body-size type: 14px/450 body and 12px/450 meta are both above the accessibility floor for a
  desktop surface; no legibility risk at this scale.
- Sticky header: reserved at 48px, not painted over — held empty on the right so sign-in causes
  zero layout shift when the shell's ⌘K mounts.
- Collision readable: grid structure is present (12-col master, 40px control rhythm) but almost
  entirely idle; the one surface-parent touch is the single serif line in the header and the
  explicit choice to keep it out of the error state. A stranger checking this against the
  collision sentence would see the grid doing all the work and the margin voice nearly silent —
  which is the point on the calmest surface, not a miss.
- Composition differs from neighbors: `centered-statement` / `flat-surface` is reserved for this
  surface; role-home (next) is `dense-grid` territory by the concept brief, so no repeat.
  Contrast with itself: not repeating the concept's own dominant token before it's even been
  used once tells the conductor's later check something true about a five-surface set, not a
  token gamed for variety.
- No invented brand, no invented person, no lorem, no fabricated data — copy is either the
  system's real name or the live app's actual field labels.
- Would a designer put their name on this: yes, with the two flags above stated rather than
  hidden — a spec that asserts ratios pass without checking is the coded-comp mode's version of
  garbled text, and I'd rather ship the honest marginal miss than a false clean pass.

---

**Return summary**

- Comp path: `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/chart-table/01-login.md`
- Composition anchor: `centered-statement`
- Background mode: `flat-surface`
- One line: a single 400px card, true-centered then optically nudged, on one flat substrate,
  with the 12-col master grid and the marginalia serif both present but almost entirely idle —
  the system shown at rest, not yet doing the work surfaces 2–7 will show it doing.
- Unsatisfied: (1) white-on-accent-emphasis computes to 4.41:1 against the dispatch's own
  ≥4.5:1 expectation — real, small, flagged, not silently patched. (2) hairline-on-substrate at
  1.31:1 is thin for an input's only boundary signal under WCAG 1.4.11 — flagged for Loop 1,
  not fixed here since it's a base-palette value. (3) the three non-dormant ring hues
  (confirmed/pending/error/draft/closed) are given as hue angles only in the dispatch; this
  surface estimated one full OKLCH triplet (the dormant confirmed ring) and flagged it for
  confirmation before surfaces 2–4 build out the full five-state ring family.
