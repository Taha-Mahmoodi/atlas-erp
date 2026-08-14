# TRANSLATE.md — atlas-console

Run: the whole authenticated Atlas ERP app shell (login → `AppShell` → 11 modules: finance,
inventory, manufacturing, HR, CRM, sales, procurement, projects, quality, maintenance,
admin, reporting). One surface, not one per module — same shell, same operator, same
session. A public marketing site, if one ever exists, would be a separate page-shaped run.

## 1. Surface class

**tool-shaped.** Derived, not asked: single `AuthGate` → `AppShell`, eleven business
modules meant to be opened daily for hours by the same operator running a company on it —
the canonical tool-shaped case (`TRANSLATE.md`'s own example: "a dashboard, an internal
tool, a console"). No disagreement between "read daily" and "read for hours" — both point
the same way. Flag for Taha to overturn at Gate A if wrong; not blocking the scout.

## 2. Viewer and their decision or task

**Multiple real operator roles, not one power-user persona** — Taha's own words: "managers,
suppliers, buyers, sellers, orgs, each doing what Atlas is for, running their enterprise."
Legitimate as a general answer for industry-agnostic, multi-role ERP (`TRANSLATE.md`'s own
escape valve for a surface with no single decision-maker) — but it sharpens to a concrete
design requirement rather than staying vague: **the system must read as coherent across many
distinct daily-use roles, each seeing and acting on their own slice**, not one dashboard
serving an imagined average user. Directly consistent with `CURRENT.md`'s absence-sweep
finding that role-shaped navigation (`TOOLS.md` §7 — "an operator does not see admin sections
they cannot use") does not exist yet. A manager approving, a buyer placing a PO, a seller
closing an order are different moments in the same system, not the same moment worn by
different job titles.

## 3. The three-second feel

Asked verbatim: *"What is the one thing you want someone to remember after they see this for
the first time?"* Taha's answer: **"different — not the usual bland and dry ERP systems."**
Distinctiveness against the category itself is the memorable thing, not a specific mood word.
Reads directly against `PRINCIPLES.md` §1's failure mode (the obvious, expected, seen-it-before
choice) and doubles as evidence for row 5 below — the "bland and dry ERP" cliché is exactly
what anti-positioning has to name and refuse.

## 4. Archetype and shadow

**Archetype: precise, rigorous, honest about its own limits.** Confirmed by Taha ("no it looks
good") against the draft read from Atlas's own words in `README.md`/`DECISIONS.md` — "derives
its scope from a researched parity map" rather than inventing one, "kept honest" with every
capability marked full/partial/out-of-scope with reasons, enforcement designed to need "zero
cooperation from query authors." **Shadow: sterile, cold, spreadsheet-generic** — the thing
"rigorous enterprise software" becomes when nobody fights for it not to. Row 3's answer is
this same tension from the other side: precise-and-rigorous must not read as bland-and-dry.

## 5. Anti-positioning

Derived from reaction to four named `STYLES.md` directions, spread across different families
— a genuine "no, never that" on three, a considered exception on the fourth:

- **Rejected outright: Glassmorphism / liquid glass, Neo-brutalism, Cinematic dark.** Not
  polite disinterest — a clean no on all three. None of them get proposed as a concept
  direction.
- **Explicitly not rejected: Claymorphism.** Taha's own words: "I think is going to look good
  if used carefully, tastefully, and very minimal." Not a mandate to use it — a live idea worth
  a concept exploring, gated hard on `STYLES.md`'s own warning for this family ("fails as
  childish, which sinks a senior claim faster than anything else on this page... right when
  the audience is consumer and the copy stays serious") — the opposite of this surface's
  archetype unless restraint does almost all the work. If a concept uses it, `DIRECTION.md`
  states explicitly what kept it from tipping into consumer/toy against row 4's shadow.
- **The named cliché fence, from row 3:** "the usual bland and dry ERP system" — beige/gray
  corporate dashboards, generic admin-template look, is the thing this run exists to not be.

## Gate A — rejected in full, corrected 2026-08-14

All three Loop 1 concepts (gauge-house, chart-table, press-panel) were rejected outright at
Gate A. Not a pick-one-and-fix-it rejection — the whole register was wrong: data-brutalist ×
{blueprint, editorial-marginalia, claymorphism-restrained}, one muted copper (58°) accent
sampled per `PRINCIPLES.md` §6's no-brand path, sharp/hairline construction throughout. Taha's
words: *"i did not like none of the concepts... the images i uploaded are more of what i
envision, and also the color i did not like the colors you chose."* Nine reference images
supplied, saved to `runs/atlas-console/references/1.png`–`9.png`. This corrects rows 5 and 6
below rather than replacing them — the corpus's own rule for a rejected gate: `TRANSLATE.md`
was wrong, not the work.

**Read across the nine references (Taha's own throughline, not this session's invention — see
the two clarifying answers below):** rounded corners throughout, not hairline/sharp-cornered
instrument-panel construction. Confident, varied hue — a 5-color donut chart, colored pipeline-
stage pills across five-plus hues, a purple/blue gradient CTA — not one muted accent over a
tinted-neutral ramp. Real depth via soft drop-shadows and, in two references, actual glass
blur. Clean modern product sidebar patterns (pill-shaped active states, avatar chips). Register
reads as **contemporary SaaS product, not technical/data-brutalist instrument panel** — the
`STYLES.md` family this run reached for last time is very likely the wrong parent entirely, not
a matter of degree.

**Glassmorphism — un-rejected, re-gated.** Two references (`2.png`, `6.png` in the saved set —
the light glass sidebar/dashboard and the glass context-menu popup) are genuinely glassmorphic.
Directly asked, since this reverses an explicit prior "no, never that": Taha's answer — *"glass
is back on the table, but please do it tastefully cuz it is a hard thing to do."* Same shape as
the claymorphism allowance from the first pass: not a mandate, a live direction gated hard on
restraint and craft, carrying `STYLES.md`'s own warning for the family (fails as gray rectangles
on a flat background the moment the substrate underneath isn't worth seeing through; breaks
`§10` under body copy). Neo-brutalism and cinematic dark remain rejected outright — nothing in
the new reference set argues for either.

**Light and dark — both required, at Loop 1 resolution, not deferred.** The nine references
split roughly evenly: dark (`1.png` Endel, `3.png` the "Barbara" dashboard, `5.png` the CRM
table, `8.png` Workly) and light (`2.png`/`6.png` the glass references, `4.png` "Salung", `7.png`
the Untitled-UI-style sidebar, `9.png` TrustToken). Asked directly, with the real cost named
(roughly double the comp count if done properly rather than declared as tokens and deferred):
Taha's answer — **"Both matter equally, full theme support."** Both themes get real comps this
pass, not a token declaration deferred to Loop 2.

## Gate A round 2 — rejected, corrected again 2026-08-14

Round 2 (the-yard, lightbox — bento signal-tokens and one-glass-object, 290° blue-violet, both
themes comped) was also rejected: *"sorry, this was bad too, using the same pictures try
again."* Archived at `rejected-v2/`.

**Diagnosis, recorded before a third pass** (the corpus's own rule says three rejections at one
gate means this file is wrong — correcting at two): both rejected rounds share one move — an
invented concept metaphor (calibration certificates; dispatch-board tokens; a cartographer's
one-glass-object) derived per `PRINCIPLES.md` §1–§3. The user's references are not asking for a
metaphor. They ARE the register: polished contemporary product design — Untitled-UI-grade
sidebars, Salung-grade monochrome restraint, the Barbara dashboard's confident colorful data
cards, keycap shortcut chips, small tasteful glass layers. User instructions outrank skill
defaults, so this run now **conforms to the reference register** — TRANSLATE.md's own escape
hatch, applied to a mood board rather than a named design system. §1–§3's invent-everything
mandate is suspended for this run; distinctiveness comes from execution quality and
ERP-specific information design, not from an invented metaphor. Recorded per `BREAKING.md`'s
out-loud rule.

**Round 3 shape:** two reference-faithful directions split on the axis the nine references
themselves split on — **light-led, near-monochrome, refined** (refs 4, 7, 9, 2, 6: Salung's
mono-caps labels and black CTA, Untitled UI's sidebar, TrustToken's calm blue, the glass ⌘K
palette as a small floating layer) versus **dark-led, color-confident** (refs 3, 5, 8, 1: the
Barbara dashboard's colorful stat cards and periwinkle charts, the CRM's colored pipeline
pills, Workly's gradient CTA). Glass appears as small floating layers (command palette,
popovers) in either — never a structural bar (that was round 2's rejected move).

**Color, corrected a second time:** 290° blue-violet is implicitly rejected with round 2. Round
3 samples from the references themselves: the periwinkle-blue family the references actually
use (refs 3, 8, 9) as accent, plus the multicolor categorical set (refs 3, 5) for data.

## Gate A — DECIDED 2026-08-14: porcelain

Round 3 presented two reference-faithful registers (porcelain — light-led near-monochrome
refined; night shift — dark-led color-confident). **Taha picked porcelain.** One-word answer,
no caveats, no mix requested. The approved register, as presented and accepted:

- Light-led, near-monochrome, quietly polished; full dark theme as a first-class equal.
- Sidebar: 248px, workspace switcher top, mono-caps section labels, pill active states,
  count badges on nav rows, user card pinned bottom (Untitled UI register, ref 7).
- Mono-caps labels (11px/600/.07em uppercase, monospace face) on stat cards and panel
  headers; ink-black primary button, white text (Salung register, ref 4).
- Status pills: soft tinted rounded-full (green in-stock / amber low / red out / dashed-
  outline draft), dot + label, never color alone.
- Sparklines in stat cards; monochrome paired-bar chart (gray + ink).
- One blue accent (#3f5bf6 light / #93a5ff dark family) — links, active nav, focus, filter
  chips. Everything else neutral.
- **Glass confined to floating layers only** — the ⌘K command palette (ref 6 register,
  keycap shortcut chips) and popovers. Nothing structural ever blurs. This satisfies the
  round-2 "glass tastefully" allowance in its approved final form.
- Approved tokens (starting values, contrast-verification pending at Loop 2): light bg
  #f7f7f8 / card #fff / ink #17181c / ink-2 #6b6d76 / line #e9e9ee / accent #3f5bf6; dark bg
  #131418 / card #1b1c22 / ink #eeeef2 / ink-2 #9a9ca8 / line #2a2c35 / accent #93a5ff.
  Radii 10–14px; soft two-layer shadow; Inter Variable + a monospace face for caps-labels
  and identifiers.

The approved visual is `scratchpad` artifact "Atlas Console Gate A v3", section A, four
frames (role home + items list × light/dark). Night shift is the rejected round-3 sibling —
archival record only, colorful-stat-card idea available for future reference but not part of
this direction.

## 6. What is already owned (correction)

**The 58° copper accent is rejected as a color choice** — "the color i did not like the colors
you chose" — and is not a starting point for the next pass; treat this as if no accent had been
proposed yet. `PRINCIPLES.md` §6's no-existing-brand path still applies (still no logo, no
brand mark anywhere in the repo — unchanged from the first pass), but the physical-scene
sentence that forces the next choice should reconcile against the corrected row-3/row-5 read
above — confident varied color, not a single muted earth tone — rather than reusing the first
pass's reasoning. Everything else in row 6 as originally filled (no external design system;
Tailwind v4 + self-hosted Inter Variable, both still load-bearing) is unchanged.

## 6. What is already owned

No named external design system — not GOV.UK, not Material, not a corporate DS; this row's
escape hatch does not apply. In source: Tailwind v4 (`@tailwindcss/vite`) utility CSS,
`@fontsource-variable/inter` self-hosted as the sole type family. `CURRENT.md` measured a
real, deliberately-held OKLCH system already in place (260° hue-locked tinted-neutral ramp,
accent `oklch(0.45 0.15 260)` — blue) — real prior work, not a default, but this is a
reposition: nothing here obligates keeping it. `SCOUT.md`'s draft survival list flags it as
*plausibly* load-bearing (unconfirmed outside this surface) and the self-hosted Inter file as
confirmed load-bearing. Loop 1 re-samples and decides fresh rather than trusting this table.
