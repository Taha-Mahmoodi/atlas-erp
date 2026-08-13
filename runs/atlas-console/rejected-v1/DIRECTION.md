# DIRECTION.md — atlas-console

Direction half, written by `direction-conductor` (Loop 1). Craft-conductor completes this file
at rendered-style resolution in Loop 2, after Gate A. This is the record, not the gate — Gate A
is held by the session that dispatched this agent.

**Run:** the whole authenticated Atlas ERP app shell (login → AppShell → 11 modules). One surface.
**Classification:** reposition (human-confirmed override of redesign-scout's proposed correction).
`CURRENT.md` and `SCOUT.md` are input constraints, not a blank page. Survival list honored: Inter
Variable self-hosted (kept, all three concepts), the CLAUDE.md terminology lock (item / vendor /
customer / warehouse / journal entry — held in every comp), the route structure (untouched by
this direction pass). The 260° accent hue is **not** kept — see the accent decision below, stated
as a trade, not a silent drop.

---

## 1. Surface class

**tool-shaped**, per `TRANSLATE.md` row 1, confirmed. One run for the whole authenticated shell,
not one per module.

## 2. Platform mode

**Skipped, by decision.** Web-only, desktop-only surface. No iOS/Android/phone/tablet target is
signaled anywhere in `TRANSLATE.md` row 2 or `CURRENT.md` — every named role (finance, inventory,
manufacturing, HR, CRM, sales, procurement, projects, quality, maintenance, admin, reporting) is a
desk role under `TOOLS.md` §10's own test ("if any role works away from a desk, that is a
different design"), which nothing in the intake trips. `SURFACES.md` was not read, per
`direction-conductor.md`'s own reading-list condition. Reveal-not-stretch is still addressed at
desktop breakpoints inside each concept (rail: icon-only → icon+label), but true narrow-viewport
(768/390px) redesign and any phone-native comp are out of scope for this run's N=7. Flagged as a
SAFE/RISK item below.

## 3. `ACCESS.md` §13 — all 19 applicable rows answered (13 shared + 6 tool-shaped; 4 native rows
N/A, no native target). No row deferred.

| # | Decision | Answer |
|---|---|---|
| 1 | Target size route | Primary controls (nav rows, buttons, inputs) at a real **40px** floor — closes `CURRENT.md`'s 36px gap without adopting touch's 48dp. Dense icon-only row-action clusters use the WCAG 2.5.8 spacing exception instead: 16–18px glyphs, 8px gaps → 24px centre-to-centre. Base spacing unit: **8px**, entering the scale before type. Density toggle exists; compact floor never drops control height below 40px |
| 2 | Contrast boundary | Web's 18px/14pt-bold "large text" line (3:1); everything under it is body (4.5:1) — not Apple's 17pt, this is web |
| 3 | Can the sampled accent carry body text / 3:1 graphical / neither | **Both**, confirmed by hand computation (OKLab→linear-sRGB→WCAG luminance) and independently re-verified by 9+ surface-designer workers doing the same math fresh. Ink grade (~L0.40–0.42, C0.09–0.10, H58°) clears 7–8.7:1 on the light substrate — body-legal. Emphasis grade (~L0.55–0.60) is direction-dependent: gauge-house's emphasis clears 5.06:1 (body-legal); **chart-table's and press-panel's emphasis grades measure 4.12–4.48:1 — 3:1 graphical/large-text/UI-component legal, NOT small-body-text legal** in those two directions. This is a real, multiply-confirmed finding, not an estimate — see palette corrections below |
| 4 | ⑂ Focus indicator, per concept | 2px solid accent-ink, 2px offset, `:focus-visible` only, all three concepts. Checked against substrate, against the tint badge bg (ring uses the darker ink grade, guaranteeing separation from tint hues), and inside a focused grid cell against its hover/alt-row background |
| 5 | ⑂ Sticky chrome geometry, per concept | Reserved layout space (not modal): sticky table header + left rail both get `space-sticky-header = 48px`, all three concepts, confirmed in every comp that has one. No permanent sticky footer/toast |
| 6 | Drag affordance | The one plausible drag surface (CRM kanban, future reorder lists) gets a "Move to…" button alternative per card. System rule; kanban is not one of the 7 numbered comps |
| 7 | Auth path (3.3.8) | Password stays (project-level architecture). Paste and password-manager autofill explicitly never blocked, confirmed in all three login comps. No cognitive-test CAPTCHA |
| 8 | Help's fixed slot | One "Help" entry, last item in the left rail, same relative position every screen, all three concepts |
| 9 | Landmark map / heading outline | One `h1` = screen title. One `main`, one `nav` ("Primary"), one `banner`. Skip-to-content link added, first in tab order, visible on focus — all three concepts |
| 10 | Accessible names for icon-only controls | Row-action icon clusters get per-record names ("Open BILL-2026-00003", not "Edit") — confirmed present in every items-list and detail comp. Collapsed rail icons keep full label as accessible name |
| 11 | ⑂ Reduced-motion still frame, per concept | None of the three are motion-native. gauge-house: certificate-strip reveal degrades to instant-visible. chart-table: plot markers place instantly, no tween. press-panel: clay-button press degrades to a static, art-directed "already pressed" shade |
| 12 | Script/direction/expansion budget | LTR, Latin script — no RTL/non-Latin signal anywhere in the intake. Tightest string (`PARTIALLY_DELIVERED`) checked; status containers sized to content with a stated max-width, not a fixed pixel box |
| 13 | Focus on route change / element removal | SPA route change → focus to the new screen's `h1` (`tabindex="-1"`). Row deleted → focus to next row (previous if last, table if now empty) |
| 14 | grid vs table + entered-cell state | Primary work lists (Items, Vendor Bills) are `role="grid"` — confirmed in every items-list comp, arrow/Enter/Space/Shift contract stated. Entered-cell state for inline status-selects: Enter switches to widget-editing, Escape restores grid nav |
| 15 | Combobox popup role | Item/vendor/customer reference-picker uses `listbox` |
| 16 | Modal initial focus + fallback | Confirmation modals set initial focus on Cancel (confirmed in vendor-bill-detail comps' void/approve flows). Invoker-gone fallback: focus to next row, or table if empty |
| 17 | Genuinely a menu/menubar? | No — left rail stays a plain `nav`. The one real `menu`: a row's "⋯ more actions" overflow button |
| 18 | Live-region triage | Silent: hover previews, clay-button press animation. Advisory (`status`/polite): "Saved," filtered-count changes. Imperative (`alert`/assertive): session-expiry, a failed save without preserved input, conflict-detected — conflict also moves focus directly to the conflict panel as a second channel, per `ACCESS.md` §7's finding that `assertive` is unreliable in JAWS/Orca/TalkBack |
| 19 | ARIA patterns as Gate B cost lines | `grid` (full keyboard contract + focus mgmt), `listbox` combobox (`aria-expanded` sync), modal dialog (focus trap + return), overflow `menu` (Tab-exits-widget), `status`/`alert` live regions. Five patterns, all traced to an actual comp |

No row deferred; no cost table needed for this section.

## 4. The derivation

Archetype (`TRANSLATE.md` row 4): **precise, rigorous, honest about its own limits.**
Shadow: **sterile, cold, spreadsheet-generic.**

Physical referents considered: a metrology lab's gauge-block certificate (a measured value ships
with its own stated tolerance); a ship navigator's chart table (a position is a fix with a stated
error circle, never a bare point); a bank auditor's reconciliation ledger (every number provable
to a receipt, a stamp marking what's checked). Atlas ERP's own architecture — the Universal
Journal, document-flow predecessor/successor chains, immutable posted entries corrected only by
reversal, an audit table of before/after diffs — is *literally* this metaphor already, which is
why these three directions read as earned rather than decorative.

**Considered and cut:** "the customs manifest" (a warehouse dock tally sheet, hand-checked against
a manifest) — dropped because it collapsed too close to gauge-house on both structural parent
(data-brutalist) and surface metaphor (stamped verification); it would likely have failed the
swap test against gauge-house, diluting the set rather than extending it. Also considered a
SCADA/control-room motion-native direction (amber telemetry on a dark substrate) — cut because,
even restrained, it reads too close to the explicitly rejected cinematic-dark family (`TRANSLATE`
row 5), not worth the anti-positioning risk when three clean, non-adjacent directions already
existed.

## 5. The sampled accent — no existing brand

`PRINCIPLES.md` §6's no-brand path applies: no logo or mark exists anywhere in the repo (checked —
no favicon, no logo file, nothing in `index.html`). One sampled accent for the whole run, per §6
("there is one logo"); every direction below reconciles against it at different chroma/lightness.

**Physical scene forcing the choice:** *the oxidized-copper stamp of a hand-verified ledger mark,
pressed by a person checking work — warm, exact, and never used decoratively.* Hue ≈ **58°**
(copper/amber, between red 29° and mustard-yellow 90°/110° on `STYLES.md`'s ramp table).

**Deliberate departure from the current 260° blue — the trade, stated once, not buried.**
`SCOUT.md` flagged the existing hue as "plausibly load-bearing… not confirmed" outside this
surface. This direction drops it anyway: `TRANSLATE.md` row 3 is an explicit comparative claim
against the ERP category itself, and blue is *the* category default (`STYLES.md`'s own cliché
table names "Blue… trust-by-convention," and blue-toned admin templates are the reflexive
default everywhere, including SAP's own Fiori branding — the named functional benchmark). Nothing
external to this surface was found using the blue. This is a reposition, explicitly asked to
reconsider the visual language, not a correction. **Cost, named:** if a marketing site or brand
asset using 260°-blue exists outside what `redesign-scout`'s extraction pass could see, this
direction breaks continuity with it — carried into SAFE/RISK below, not buried here.

**Contrast verification** (hand-computed, OKLab→linear-sRGB→WCAG-luminance, CSS Color 4
matrices — independently re-derived by 9+ surface-designer workers during dispatch, not just by
the conductor):

- Ink grade `oklch(0.42 0.09 58)` on white/near-white substrate: **≈8.3–8.7:1** (small variance
  across workers' independent recomputation, all comfortably body-legal)
- Emphasis grade, gauge-house's `oklch(0.55 0.13 58)`: **5.06:1** white-on-it — body-legal
- Emphasis grade, chart-table's `oklch(0.58 0.10 58)`: **4.29–4.48:1** — **short of 4.5:1 AA for
  small body text**, confirmed independently by 5 workers. 3:1 graphical/large-text/UI-component
  legal only in this direction
- Emphasis grade, press-panel's `oklch(0.60 0.14 58)`: **4.12–4.48:1** white label — **same
  shortfall**, confirmed independently by 4 workers, on the exact two roles (clay CTA button, clay
  pending pill) this direction's whole collision depends on

**This is the run's single most consequential correction to my own Loop 1 palette math.** All
three directions' *ink* grades are solid. Two of three directions' *emphasis* grades need a small
token nudge (~0.04–0.06 lightness down, per the workers' own suggested fix, or a bold/large-text
qualifying label) before Loop 2 locks `tokens.json`. Flagged here rather than silently rounded up
by any one of the 21 workers who found it — none of them "fixed" it unilaterally, which is the
right call; it isn't theirs to change.

## 6–8. The three concepts

Each concept carries its direction's palette and type, developed by the conductor per
`loops/01-direction.md` §7, not generated by a worker.

### A — gauge-house

**Collision (structural parent named):** data-brutalist (structure) × blueprint (surface) — *"A
technical drawing is flat and authoritative by convention; giving each number a stamped
calibration certificate — measured value, tolerance, checked-by, date — makes precision something
the operator can audit on the spot rather than take on faith."*

**Opening move:** the role-home renders as a title-block header (module, role, "as of" timestamp)
above one dense ranked worklist, each row carrying a technical-drawing leader-line annotation
explaining *why* it's on the list ("3 days overdue," "GRN mismatch: qty −4") — no KPI-card grid,
no freestanding decoration.

**Primary content:** real `role="grid"` tables, tabular-nums, decimal-aligned money, hairline row
dividers. Selecting a record opens a persistent "certificate strip" — a vertical annotated
timeline of that document's predecessor/successor chain (PO→GRN→Bill), each stage stamped with a
measured value, tolerance/variance, checked-by, and date, matching Atlas ERP's real document-flow
architecture rather than an invented metaphor.

**Navigation:** left rail icon-only at rest, reveals icon+label on focus/hover (reveal-not-
stretch, confirmed in the role-home comp's exact numbers), persistent ⌘K search/go-to in the
sticky header.

**Missing/wrong (TOOLS.md's nine states, empty/permission-denied/conflict named specifically):**
Empty renders as an unstamped, blank certificate template with one "Log the first item" action
where the stamp would go; filtered-empty is distinct copy plus a visible clear-filters chip.
Error (the live app's silent bad-ID bug) renders as a stamped "VOID / NOT FOUND" certificate
naming what happened, confirming nothing was lost, with a clear next action. Permission denied
would render as a certificate stamped "ACCESS RESTRICTED" naming who to ask (not comp'd in this
N=7, stated as the pattern). Conflict renders as two stamped certificates side by side with a
diff, forcing the human to choose — implementing `TOOLS.md`'s "show both, let the human choose"
literally.

**Palette (light):** substrate `oklch(0.985 0.003 58)` · primary text `oklch(0.20 0.01 58)` ·
secondary text `oklch(0.45 0.012 58)` · hairline border `oklch(0.88 0.008 58)` (**measures
~1.38:1 on substrate — decorative-only, confirmed by 3 independent workers; below the 3:1
non-text floor, fine where hairlines are not the sole boundary signal, a real gap wherever they
would be the only one**) · accent-ink `oklch(0.42 0.09 58)` (≈8.3–8.7:1, body-legal) ·
accent-emphasis `oklch(0.55 0.13 58)` (5.06:1 white-on-it, body-legal) · accent-tint
`oklch(0.94 0.03 58)` (≈7.27:1 w/ ink text). Dark: substrate `oklch(0.18 0.006 58)` · text
`oklch(0.94 0.006 58)` · accent-dark `oklch(0.72 0.10 58)` (target ≥4.5:1, computed 7.40:1 by one
worker's independent check — clears with margin).

**Status vocabulary** (shape+label, never color alone): Draft = neutral gray chip, dashed border;
Pending = blue-gray chip (H≈240°) + clock glyph; Posted/Active = green chip `oklch(0.95 0.03
150)`/`oklch(0.5 0.12 150)` text (reused from `CURRENT.md`'s already-verified green, not the
brand accent) + check glyph; Error/Overdue = red chip, text `oklch(0.5 0.18 25)` (reused,
already-verified) + exclaim glyph; Closed = dark-neutral chip, label only. **Note:** full
canonical OKLCH triples for Draft/Pending/Closed backgrounds were not fully specified in my
dispatch (only hue angles or "neutral gray/dark-neutral" given) — multiple workers independently
extrapolated plausible values; these need **one** canonical reconciliation pass before Loop 2,
not five independently-guessed ones. Listed under "could not do," below.

**Type:** Inter Variable (self-hosted, load-bearing, kept — reason: already owned, tabular
figures, wide weight range for dense data) primary; IBM Plex Mono Variable, self-hosted, for
identifiers/document numbers only (ITM-BOLT, BILL-2026-00003) — reason: fixed-width parsing,
Inter's proportional digits blur codes at a skim. Tabular-nums on every numeric column.
Role-indexed: screen title 20px/600 (kept from the current app's own zero-exception H1) ·
section-eyebrow 12px/600 caps (kept) · body/data 14px/450 tabular · meta 12px/450 ·
mono-identifier 13px/500.

**Style-under-density:** *at forty rows this is data-brutalist operating at its designed load —
hairlines and tabular figures were built for this; the certificate-strip annotation confines
itself to the selected row, never decorating all forty at once, so density costs nothing extra.*
Confirmed structurally by the role-home comp's own row-count math (18 rows visible of ~40, the
certificate strip only exists on selection).

**Surfaces (N=7, screen-flow order):** 01 login · 02 role home · 03 items list (dense grid) ·
04 vendor bill detail (document flow / certificate strip) · 05 new item form · 06 empty state
(filtered) · 07 error state (fixes the silent bad-ID bug).

### B — chart-table

**Collision:** Swiss/International grid (structure) × editorial marginalia (surface) — *"The grid
asserts machine order; a navigator's penciled correction in the margin asserts a human hand
checked it — together the surface reads instrument-precise and human-verified at once, which a
spreadsheet cannot claim."*

**Opening move:** role-home is a strict named-grid column layout holding the day's tasks as a
plotted sequence — each task a small "fix" marker (ring thickness = certainty: thin solid =
confirmed, dashed = estimate/pending) along a horizontal "today" axis, with exactly one marginal
note in a serif face beside the busiest cluster ("Six vendor bills cross their due date today —
three from the same supplier"). The grid is legible in three seconds; the margin is where
judgment lives.

**Primary content:** dense tables (`role="grid"` where cells are interactive), decimal-aligned,
but status renders as plotted-fix ring markers, not chips — the direction's signature difference
from A and C. A running head at the top of every screen behaves as a breadcrumb-as-title, set in
the marginalia serif.

**Navigation:** left rail is a named-grid column at rest (not icon-collapsing — the grid's own
logic keeps it a full labeled column, a deliberate contrast with A and C's icon-only rest state),
persistent ⌘K search in header.

**Missing/wrong:** Empty is an axis with no plotted fixes and one marginal note ("Nothing plotted
yet. Log the first item to start today's chart."). Filtered-empty is the same axis with a visible
filter chip and clear action. Error (bad-ID) renders as a heavy-ring error marker on the axis with
a plain-worded margin note naming what happened and confirming nothing was lost. Conflict renders
as two fixes plotted at the same point with different confidence rings, a margin note naming both
authors, letting the human pick.

**Palette (light):** substrate `oklch(0.99 0.002 58)` (flatter/cooler than A) · primary text
`oklch(0.22 0.008 58)` · secondary `oklch(0.46 0.01 58)` · hairline `oklch(0.90 0.006 58)`
(**measures ~1.31:1, confirmed by 4 independent workers — same decorative-only caveat as A**) ·
accent-ink (muted, "penciled") `oklch(0.40 0.07 58)` (≈7–9.4:1 across independent checks,
body-legal) · **accent-emphasis `oklch(0.58 0.10 58)` — measures 4.29–4.48:1, confirmed by 5
independent workers doing real OKLab math. Legal for 3:1 graphical/large-text/UI-component roles
only in this direction, NOT small body text at 4.5:1.** accent-tint `oklch(0.95 0.02 58)`. Dark:
substrate `oklch(0.16 0.004 58)` · text `oklch(0.93 0.005 58)` · accent-dark `oklch(0.70 0.08 58)`
(target ≥4.5:1, not independently re-verified by a worker in this round — flagged for Loop 2).

**Status vocabulary rendered as "plotted-fix" ring markers**, not chips — same canonical five
states, different grammar than A: thin solid ring = confirmed/posted (green H≈145°); dashed ring
= pending/estimate (blue-gray H≈240°); heavy ring = error/overdue (red H≈25°); hollow gray ring =
draft (**one worker computed this specific pairing at 2.16:1 — fails even the 3:1 non-text floor;
this token needs a real fix, not just a caveat, wherever "draft" appears as a hollow ring**);
filled dark ring = closed.

**Type:** Inter Variable primary (same reason as A, kept as the default pair). Source Serif 4
Variable, self-hosted, reserved *only* for the marginalia/annotation layer (running-head-as-
breadcrumb, margin notes) — reason: marks that layer as commentary distinct from the grid's data,
serving the collision's surface parent directly. Role-indexed: title 20px/600 · running-head/
margin serif 13px italic/400 · body/data 14px/450 tabular · meta 12px/450.

**Style-under-density:** *Swiss/table holds density natively — a table is a grid with the lines
turned on. The margin column is the risk: at forty rows it cannot carry a note per row, so it
collapses to the two or three loudest patterns only — dense grid, sparse commentary*, per
`STYLES.md`'s own bimodal-density worked answer. Confirmed structurally: the items-list comp
places exactly 2 margin notes across ~40 rows, not one per row, by explicit design.

**Surfaces (N=7, same order as A):** 01 login · 02 role home · 03 items list · 04 vendor bill
detail · 05 new item form · 06 empty state (filtered) · 07 error state.

### C — press-panel

**Collision:** data-brutalist (dominant/structure) × claymorphism (bounded/surface, gated on
restraint) — *"A flat instrument panel is legible because nothing on it competes for the
operator's hand; give it exactly one dimensional, pressable object — the primary action — and
that object becomes the only thing the hand knows to reach for, without asking the rest of the
panel to lie about being flat."* This is the literal execution of the human's own words on row 5
("claymorphism… used carefully, tastefully, and very minimal") — **claymorphism is confined to
exactly two roles system-wide: the primary/confirming CTA button, and the "pending/in-progress"
status pill. Never on cards, containers, panels, or body chrome.** Every one of the 7 comps was
independently audited by its own worker for this two-role limit and confirmed to hold.

**Opening move:** the flattest surface of the three concepts — an engraved-line worklist with no
cards, no shadows anywhere except one: the day's single most important action (e.g., "Approve 6
pending vendor bills") rendered as one raised, embossed copper button, visibly the only thing on
the panel with any give. Every other button on the same screen, including other row-level
actions, stays flat/bordered/quiet.

**Primary content:** dense flat table (`role="grid"`), tabular figures, hairline rules — the
closest of the three to A's density discipline, with zero annotation layer (no blueprint
marginalia, no chart-table plotting): this direction is the plainest everywhere except its one
clay object, which is the entire point of the collision.

**Navigation:** icon-only rail at rest (reveal-not-stretch), ⌘K search.

**Missing/wrong:** Empty doubles as the demonstration of what the clay treatment is for — the one
embossed button reads "Log first item," making unmistakable which thing to press; copy is the
plainest of the three ("Nothing here yet."). Error/not-found is deliberately the least-clayed
surface in the whole set — one worker's comp correctly withheld even the "confirming action"
clay treatment on the Back-to-items button, reading the surface-specific "bad news is never
clayed" instruction as overriding the concept's general allowance, and explicitly flagged that
call rather than defaulting to it silently. Permission denied and conflict follow the same
"never clayed" rule (stated as the pattern, not comp'd in this N=7).

**Palette (light):** substrate `oklch(0.98 0.002 58)` ("brushed steel," coolest/flattest of the
three — deliberately, so the one clay object visually pops) · primary text
`oklch(0.19 0.006 58)` · secondary `oklch(0.44 0.008 58)` · hairline `oklch(0.86 0.005 58)`
(**measures ~1.45:1, confirmed by 3 independent workers — same decorative-only caveat**) ·
accent-ink `oklch(0.40 0.10 58)` (body-legal, in-family with A's verified pair) ·
**accent-emphasis `oklch(0.60 0.14 58)` — clay button/pill only, richest chroma of the three
directions — measures 4.12–4.48:1 white-on-it, confirmed by 4 independent workers. Short of
4.5:1 for the button's 15px/600 label, which does not clear the web's 18px/14pt-bold large-text
line.** accent-tint `oklch(0.93 0.035 58)`. Clay spec: radius 16–20px, layered soft shadow pair,
one fixed light-source direction held identical in light and dark mode (per `STYLES.md`'s
neumorphism-inversion warning), hard 2px `:focus-visible` ring — never a deeper shadow standing in
for focus, confirmed present on every clay element across all 7 comps. Dark: substrate
`oklch(0.17 0.004 58)` · text `oklch(0.92 0.004 58)` · clay shadow direction fixed, hue/surface
retuned (not independently re-verified by a worker this round).

**Status vocabulary:** canonical five states, flat chips for draft/posted/error/closed; pending is
the *only* clay-rendered pill — confirmed as the second of the two permitted clay roles in every
comp that has a pending state.

**Type:** Inter Variable only — no second family. Reason stated on the line: "a flat panel with
one dimensional button is a material distinction, not a typographic one; a second face would
compete with the one thing this direction wants noticed." Role-indexed: title 20px/600 ·
body/data 14px/450 tabular · meta 12px/450 · clay-button label 15px/600.

**Style-under-density:** *data-brutalist is the stricter parent — forty rows is its designed
load. The gate is the clay role staying confined to one button and one pill per screen; if it
migrated onto rows, forty soft shadows would stutter the compositor. Confined as specified, cost
is flat regardless of row count.* Confirmed structurally: the items-list comp's own audit table
proves zero clay instances on any of its 17 populated rows or their row-action clusters.

**Surfaces (N=7, same order as A/B):** 01 login · 02 role home · 03 items list · 04 vendor bill
detail · 05 new item form · 06 empty state (filtered) · 07 error state.

## 9. The two distinctness tests + category-reflex check

**Swap test.** Screen titles/registers differ: gauge-house uses cert/log language ("Item Log,"
implied certificate framing); chart-table stays plain in titles but shifts in status/empty-state
language; press-panel is the plainest register throughout. The clearest probe — empty-state copy
— is unmistakably distinct: A *"No certificate on file. Log the first item to open one."* B
*"Nothing plotted yet. Log the first item to start today's chart."* C *"Nothing here yet."* None
of the three reads as a valid swap into another. **Passes.**

**Family pass.** Labels: **gauge-house / chart-table / press-panel** — three concrete,
non-overlapping real-object nouns, no shared vocabulary. **Passes** (the fresh-judge half — human
matching label to concept before seeing them — happens at Gate A, per spec, not here).

**Category-reflex check.** None of the three are guessable from "surface for an ERP" or "ERP plus
obvious twist" — not "ERP but dark," not "ERP but bento," not "ERP but glassy." All three trace to
non-obvious physical referents tied directly to the archetype rather than a category reflex.
**Passes.**

## 10. The set-level check

Run once per concept, on the tokens each of the 21 independent `surface-designer` workers logged
in its own file — read off disk, not out of return messages, per `loops/01-direction.md` §10.
**Not self-graded**: 21 independent workers ran, none of them could see any other worker's output
or token choice, which is exactly the check's valid-use case.

### Composition log

| # | Surface | gauge-house (anchor / bg) | chart-table (anchor / bg) | press-panel (anchor / bg) |
|---|---|---|---|---|
| 01 | Login | stacked-center / textured-surface | centered-statement / flat-surface | centered-statement / flat-surface |
| 02 | Role home | dense-grid / flat-surface | dense-grid / flat-surface | dense-grid / flat-surface |
| 03 | Items list | dense-grid / flat-surface | dense-grid / flat-surface | dense-grid / flat-surface |
| 04 | Vendor bill detail | right-rail-caption / textured-surface | right-rail-caption / flat-surface | dense-grid / flat-surface |
| 05 | New item form | stacked-center / textured-surface | right-rail-caption / flat-surface | dense-grid / flat-surface |
| 06 | Empty state | centered-statement / flat-surface | stacked-center / flat-surface | stacked-center / flat-surface |
| 07 | Error state | centered-statement / textured-surface | right-rail-caption / textured-surface | centered-statement / flat-surface |

### The three anti-repeat criteria — suspended in full, and why

**All three criteria are suspended for this entire run**, per `loops/01-direction.md` §10's
explicit tool-shaped carve-out: *"Suspended on a tool-shaped set — all three criteria, not only
the background one… nine screens honestly log flat-surface throughout, dense-grid is the correct
anchor for consecutive table screens, and a dashboard carrying a full-bleed treatment somewhere in
it has a defect rather than a range."* This run has no page-shaped subset (every one of the 21
comps is a tool-shaped desktop screen), so the suspension applies wholesale, not selectively.

Stated plainly so a later reader does not mistake a uniform set for an oversight: press-panel logs
`flat-surface` on all 7 surfaces and `dense-grid` on 4 consecutive surfaces (02–05) — both would
fail the raw criteria, and both are *correct* here: an instrument-panel direction whose whole
argument is restraint should not manufacture background variety it doesn't mean, and role-home /
items-list / vendor-bill-detail / new-item-form are genuinely all table-or-field-grid-dominant
screens. chart-table logs `flat-surface` on 6 of 7 (all but the textured error-state). gauge-house
is the most varied of the three by construction (textured-surface appears on 4 of 7, alternating
with flat-surface), which tracks its blueprint-grid surface parent rather than indicating a
different quality bar.

**No full-bleed treatment appears anywhere in any of the three sets** — also correct and also
suspended: a data console has no hero-image screen to justify one; forcing one in would be
decoration, not range.

The real distinctness burden for this class sits on the swap test and family pass (§9 above,
passed) and on what a set must *never* vary (below), not on composition variety.

### What a set must never vary — checked, not suspended

**Within each concept**, palette, type hierarchy, component family, and surface treatment stay
identical across all 7 comps. Confirmed: every surface within gauge-house quotes the same six
core OKLCH tokens verbatim (workers independently re-derived contrast on them and got consistent
numbers, which is itself evidence of consistency rather than drift); chart-table's accent-emphasis
shortfall (4.29–4.48:1) recurs identically across 5 separate surfaces rather than varying, which
is what "identical treatment" looks like when a token has a real problem — it's wrong everywhere
uniformly, not wrong on some surfaces and fine on others; press-panel's two-role clay restraint
was independently audited and held on every surface that has a CTA or a pending state. **Passes**,
per concept.

**Across concepts, palette and type differ**, as required: gauge-house adds a mono face (IBM Plex
Mono) and the warmest substrate tint; chart-table adds a serif (Source Serif 4) and the most
muted/cooled accent chroma; press-panel adds no second face and the coolest/flattest neutral ramp
paired with the single richest accent chroma, reserved for exactly two bounded roles. **Passes.**

No offending surfaces to reject or regenerate.

## 11. Coded-comp disclosure

**Ratios computed, not observed; first render happens at build.** Every contrast figure in this
document and in all 21 comp files was derived by hand or by a throwaway script (OKLab→linear-
sRGB→WCAG luminance), independently, by the conductor and by the workers who each re-derived the
core pairs fresh rather than trusting the dispatched numbers blind — which is how the
chart-table/press-panel emphasis-grade shortfall was actually caught. Nothing here has rendered in
a browser yet.
