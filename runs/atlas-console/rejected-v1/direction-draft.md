# direction-draft.md — atlas-console Loop 1

Written as-I-go per direction-conductor.md. This is reasoning, not the gate package (that goes
in the final message and DIRECTION.md).

## 0. Branch confirmation
Reposition, taken by the human already (redesign-scout proposed correction; human overrode).
This loop runs in full. CURRENT.md is an input constraint, not a blank page. Survival list from
SCOUT.md treated as real: Inter Variable self-hosted (confirmed load-bearing), 150+ routes
(load-bearing as a category, not per-URL), CLAUDE.md terminology lock (item/vendor/customer/
warehouse/journal entry — hard, project-level, independent of this run), 260° accent hue
(plausibly load-bearing, NOT confirmed — this run is free to change it and does; trade recorded
below).

## 1. Surface class
tool-shaped. Confirmed from TRANSLATE.md row 1, one surface for the whole authenticated shell
(not one run per module).

## 2. Platform mode
Skipped. Web-only, desktop-only surface — no iOS/Android native target, no phone/tablet target
signaled anywhere in TRANSLATE.md row 2 or CURRENT.md (ERP back-office roles: finance, inventory,
manufacturing, HR, CRM, sales, procurement, projects, quality, maintenance, admin, reporting — desk
roles, not field roles per TOOLS.md §10's "if any role works away from a desk, that is a different
design" trigger, which nothing here trips). SURFACES.md not read, per direction-conductor.md's own
reading-list condition. Recorded as a decision, not a silent omission: **if a field-mobile role
(e.g., a warehouse floor operator) turns out to be real, that is a separate run, not a breakpoint
retrofit onto this one** — flagged as a SAFE/RISK item in the final package.

Desktop reveal-not-stretch is still addressed at desktop breakpoints (1440→1024) inside the
concepts themselves: rail goes icon-only → icon+label, never a stretched wide layout with nothing
new revealed. True narrow-viewport (768/390) redesign is out of scope for the N=7 comps.

## 3. ACCESS.md §13 — all 19 applicable rows (13 shared + 6 tool-shaped; 4 native rows N/A, no
native target)

1. **Target size route.** Primary controls (nav rail rows, buttons, form inputs) get a real 40px
   min height — closing CURRENT.md's 36px gap without adopting Material's 48dp touch floor (this
   is pointer/keyboard-primary, not touch). Dense icon-only row-action clusters use the WCAG 2.5.8
   spacing exception instead: 16–18px glyphs, 8px gaps → 24px centre-to-centre. Base spacing unit:
   8px, entering the scale before type. A density toggle (comfortable/compact) exists; compact
   floor never drops control height below 40px.
2. **Contrast boundary.** Web's 18px/14pt-bold "large text" line (3:1); everything under it is
   body (4.5:1). Not Apple's 17pt — this is web, not iOS.
3. **Can the sampled accent carry body text / 3:1 graphical / neither?** Both. Computed by hand
   (OKLab→linear-sRGB→relative-luminance, CSS Color 4 matrices) for the shared 58° hue:
   - `oklch(0.42 0.09 58)` on `oklch(0.985 0.003 58)` substrate ≈ **8.71:1** (body-legal)
   - `oklch(0.55 0.13 58)` with white label ≈ **5.06:1** (clears both 3:1 graphical AND 4.5:1)
   - `oklch(0.94 0.03 58)` tint bg with `oklch(0.42 0.09 58)` text ≈ **7.27:1**
   All three verified in-gamut (b_lin ≥ 0 at each). Flagged: computed, not rendered — the
   mandatory coded-comp disclosure applies to every number in this run.
4. **⑂ Focus indicator, per concept.** 2px solid accent-ink, 2px offset, `:focus-visible` only.
   Checked against substrate (passes 1.4.11's 3:1 easily at ~8.7:1... well the ring itself is a
   UI object not text, but same color clears 3:1 trivially), against the tint badge bg (ring uses
   the darker ink grade, not the tint hue, guaranteeing separation), and inside a focused grid
   cell against its hover/alt-row background — not just the base substrate.
5. **⑂ Sticky chrome geometry, per concept.** Reserved layout space (not modal): sticky table
   header + left rail both get `space-sticky-header = 48px` as a named token, so `scroll-padding`
   can reserve it. No permanent sticky footer/toast; toasts are dismissible/auto-clearing, not
   fixed chrome.
6. **Drag affordance.** The one plausible drag surface (CRM kanban, and any future reorder list)
   gets a "Move to…" button alternative per card — a real control, not hover-only. Declared as a
   system rule; kanban is not one of the 7 numbered comps but the rule applies wherever the system
   grows into it.
7. **Auth path (3.3.8).** Password stays (project-level architecture, JWT+argon2 — not mine to
   remove). Paste-into-password-field and password-manager autofill explicitly never blocked. No
   cognitive-test CAPTCHA. Satisfies the Alternative exception via Mechanism (platform password
   managers), no new UI needed.
8. **Help's fixed slot.** One "Help" entry, last item in the left rail, same relative position on
   every screen across all three concepts — satisfies 3.2.6 even with no help content yet.
9. **Landmark map / heading outline.** One `h1` = screen title per screen. One `main`, one `nav`
   (labeled "Primary"), one `banner`. Skip-to-content link added (CURRENT.md found none), first in
   tab order, visible on focus.
10. **Accessible names for icon-only controls, as strings.** Row-action icon clusters get
    per-record names — "Open BILL-2026-00003", "Duplicate BILL-2026-00003", "Void
    BILL-2026-00003" — never "Edit" ×11. Collapsed rail icons keep their full label as accessible
    name even when visually icon-only.
11. **⑂ Reduced-motion still frame, per concept.** None of the three are motion-native, so this is
    low-stakes but not skipped: A's certificate-strip reveal degrades to instant-visible; B's plot
    markers place instantly, no tween; C's clay-button press degrades to a static, art-directed
    "already pressed" shade — not a flat disabled look.
12. **Script/direction/expansion budget.** LTR, Latin script — CLAUDE.md's terminology lock is
    English, no RTL/non-Latin signal anywhere in the intake. Tightest string checked:
    `PARTIALLY_DELIVERED` (CURRENT.md's longest observed status word) — status containers sized to
    content with a stated max-width, not a fixed pixel box, giving ~2× hygiene margin for future
    relabeling even though no translation is in scope now.
13. **Focus on route change / element removal.** SPA route change (TanStack Router) → focus moves
    to the new screen's `h1`, made programmatically focusable (`tabindex="-1"`) — announces title,
    Tab continues into content. Row deleted from a list → focus to next row (previous if last,
    table itself if now empty) — matches ACCESS §6's table exactly.

Tool-shaped (14–19):

14. **grid vs table, + entered-cell state.** Primary work lists (Items, Vendor Bills) are `grid`
    — interactive per-row controls, hours of daily use, matches §15's arrow/Enter/Space/Shift
    contract. Read-only reference lists (link-per-row only) stay plain `<table>`. Entered-cell
    state: a grid cell holding an inline status-select — Enter switches to widget-editing (arrows
    now drive the select), Escape restores grid navigation. Declared explicitly, shared mechanic
    across all three concepts' visual skins.
15. **Combobox popup role.** The item/vendor/customer reference-picker uses `listbox` — flat
    filtered list, the ordinary case. (No multi-column person-picker exists in these 7 comps; not
    fabricated.)
16. **Modal initial focus + fallback.** Confirmation modals set initial focus on the
    least-destructive action (Cancel, not Delete). If the invoker (the row) is gone after its own
    delete, focus returns to the next row, or the table if now empty.
17. **Genuinely a menu/menubar?** No — left rail stays a plain `nav` of links. The one real `menu`
    role: a row's overflow ("⋯ more actions") button — Duplicate / Archive / Void — a genuine
    application action menu, correctly scoped.
18. **Live-region triage.** Silent: hover previews, clay-button press animation. Advisory
    (`status`/polite): "Saved," "3 rows updated," filtered-count changes. Imperative
    (`alert`/assertive): session-expiry warning, a save that failed without preserving input
    (should be rare per TOOLS §5), and conflict-detected — which per ACCESS §7's finding that
    `assertive` is unreliable in JAWS/Orca/TalkBack, also moves focus directly to the conflict
    panel as a second channel, not aria-live alone.
19. **ARIA patterns as Gate B cost lines.** `grid` (full keyboard contract + focus mgmt),
    `listbox` combobox (`aria-expanded` sync), modal dialog (focus trap + return), overflow `menu`
    (Tab-exits-widget contract), `status`/`alert` live regions. Five patterns, all traced to an
    actual comp — nothing invented beyond what the 7 surfaces need.

No row deferred. All 19 answered at Loop 1 resolution.

## 4. Derivation — archetype → physical scene → three directions

Archetype (row 4): "precise, rigorous, honest about its own limits." Shadow: "sterile, cold,
spreadsheet-generic."

Real-world referents brainstormed: a metrology lab's gauge-block certificate (a measured value
ships with its own stated tolerance); a ship navigator's chart table (a position is never a
point, it's a fix with a stated error circle); a bank auditor's reconciliation ledger (every
number provable to a receipt, a rubber stamp marking what's checked); a structural engineer's
stamped drawing set; a customs dock's hand-tallied manifest. Atlas ERP's own architecture
(Universal Journal, document-flow predecessor/successor chain, immutable posted entries,
correction-via-reversal, an audit table of before/after diffs) is *literally* this metaphor
already, not invented flavor — a genuine gift for this derivation.

Considered and cut: "the customs manifest" — collapsed too close to gauge-house on both
structural parent (data-brutalist) and surface metaphor (stamped verification); would likely fail
the swap test against it, so dropped rather than diluting the set. Also considered a SCADA/
control-room motion-native direction (amber telemetry, dark substrate) — cut because it reads too
close to the explicitly-rejected cinematic-dark family even restrained, not worth the anti-
positioning risk against row 5 when three clean, non-adjacent directions already exist.

Three surviving directions (each a concrete sentence, not adjectives):

- **A — gauge-house.** "A metrology lab's gauge-block certificate wall — hairline-ruled tables
  where every number carries its own stamped tolerance and calibration date." Parents:
  data-brutalist (structure) × blueprint (surface).
- **B — chart-table.** "A ship navigator's chart table, dead-reckoning corrected: a plotted
  position with its stated margin of error, penciled bearing lines meeting at a hand-checked
  fix." Parents: Swiss/International (structure) × editorial marginalia (surface).
- **C — press-panel.** "A brushed-steel calibration panel, engraved flat and precise, with one
  embossed brass press-button — the only part of the panel that has any give." Parents:
  data-brutalist (dominant/structure) × claymorphism (bounded/surface, exactly two roles: the
  primary CTA and one status-pill — this is the human's explicit "claymorphism, used carefully,
  tastefully, very minimal" instruction taken literally).

Picking-one check: (1) category cluster — generic Bootstrap/Material admin templates, blue
accent, card-wrapped tables; all three directions structurally differ. (2) empty position —
nobody in ERP-land uses a calibration-cert, chart-table, or instrument-panel visual grammar as
literal metaphor. (3) anti-positioning — none use glassmorphism/neo-brutalism/cinematic-dark;
claymorphism appears exactly once, gated to two bounded roles in C, restrained per the human's own
condition. (4) risk appetite — tool-shaped, high tolerance for anything removing keystrokes
(⌘K, grid-not-table, role-shaped nav all added), near-zero tolerance for habit cost (Inter stays,
document-flow architecture stays, terminology lock honored). (5) what's owned — Inter Variable
kept as the default pair in all three (STYLES.md's fifth picking input); the 260° blue is
deliberately NOT kept (see accent decision below), with the trade stated.

## 5. Palette — one sampled accent, no existing brand

PRINCIPLES.md §6's no-brand path applies (no logo/mark anywhere in the repo, confirmed by the
dispatch). Physical scene forcing the choice: **"the oxidized-copper stamp of a hand-verified
ledger mark, pressed by a person checking work — warm, exact, and never used decoratively."**
Hue ≈ 58° (copper/amber, between red 29° and mustard-yellow 90°/110° on the STYLES.md ramp table).

**Deliberate departure from the current 260° blue — the trade, stated once.** SCOUT.md flagged
the existing hue as "plausibly load-bearing… not confirmed" outside this surface, and real prior
work rather than a default. This run drops it anyway, because: (a) TRANSLATE row 3 is an explicit
comparative claim against the ERP category, and blue is *the* category default — STYLES.md's own
cliché table names "Blue… trust-by-convention" for fintech and blue-toned admin templates are the
generic-SaaS reflex; (b) nothing external to this surface was found using the blue (no marketing
site, no printed material, no logo); (c) this is a reposition, explicitly asked to reconsider the
visual language itself, not a correction. **Cost, named:** if a marketing site or brand asset
using 260°-blue exists outside what this extraction pass could see, this direction breaks
continuity with it — a risk carried into the SAFE/RISK split below, not buried here.

Sampling method note: no logo exists to re-sample pixels from (the "re-sample the row-6 source
directly" instruction in my own agent file applies to logo/brand-asset sampling; there is none
here), so this is PRINCIPLES §6's alternate path — a deliberate choice defended by one sentence
of physical scene, reconciled against row 3 above.

**Contrast verification (hand-computed, OKLab→linear-sRGB matrices, CSS Color 4):**
- Ink grade `oklch(0.42 0.09 58)` on white/near-white substrate: **8.71:1**
- Emphasis grade `oklch(0.55 0.13 58)`, white label on it: **5.06:1**
- Tint bg `oklch(0.94 0.03 58)` with ink-grade text: **7.27:1**

All in-gamut (checked via the linear-RGB sign test — b_lin ≥ 0 at each). This hue is unusually
versatile: it clears body-text contrast at multiple lightness points, not just one, which gives
each direction real room to vary chroma/lightness without breaking the pair.

Per-direction palette build-outs, status vocabulary, type systems: see the concept sections
below (duplicated into the surface-designer dispatches verbatim, since each worker reads nothing
else).

### Concept A — gauge-house
- Substrate `oklch(0.985 0.003 58)` · primary text `oklch(0.20 0.01 58)` · secondary text
  `oklch(0.45 0.012 58)` · hairline border `oklch(0.88 0.008 58)`
- Accent-ink `oklch(0.42 0.09 58)` (≈8.71:1 on substrate) · accent-emphasis `oklch(0.55 0.13 58)`
  (≈5.06:1 white-on-it) · accent-tint `oklch(0.94 0.03 58)` (≈7.27:1 w/ ink text)
- Dark mode: substrate `oklch(0.18 0.006 58)` · primary text `oklch(0.94 0.006 58)` · accent-dark
  `oklch(0.72 0.10 58)` (target ≥4.5:1, verify at build)
- Status vocabulary (shape+label, never color alone): Draft = neutral gray chip, dashed border;
  Pending = blue-gray chip (H≈240°) + clock glyph; Posted/Active = green chip
  `oklch(0.95 0.03 150)`/`oklch(0.5 0.12 150)` text (reused from CURRENT.md's already-verified
  green, not the brand accent) + check glyph; Error/Overdue = red chip, text
  `oklch(0.5 0.18 25)` (reused, already verified) + exclaim glyph; Closed = dark-neutral chip,
  label only.
- Focus ring: 2px solid accent-ink, 2px offset, `:focus-visible` only.
- Type: Inter Variable (self-hosted, load-bearing — kept, reason: already owned, tabular figures,
  wide weight range) primary; IBM Plex Mono Variable, self-hosted, for identifiers/document
  numbers only — reason: fixed-width parsing of codes (ITM-BOLT, BILL-2026-00003) that Inter's
  proportional digits blur at a skim. Tabular-nums declared on every numeric column (TOOLS §12).
- Scale: role-indexed (component list, not prose). Screen title 20px/600 (kept — CURRENT.md's own
  zero-exception H1, a real decision worth keeping); section-eyebrow 12px/600 caps (kept); body/
  data 14px/450 tabular; meta 12px/450; mono-identifier 13px/500.
- Style-under-density: *at forty rows this is data-brutalist operating at its designed load —
  hairlines and tabular figures were built for this; the blueprint annotation (certificate strip)
  confines itself to the selected row, never decorating all forty at once, so density costs
  nothing extra.*

### Concept B — chart-table
- Substrate `oklch(0.99 0.002 58)` (flatter/cooler than A) · primary text `oklch(0.22 0.008 58)` ·
  secondary `oklch(0.46 0.01 58)` · hairline `oklch(0.90 0.006 58)`
- Accent-ink (more muted, "penciled") `oklch(0.40 0.07 58)` — in-family with A's verified pair,
  expect ≥7:1, confirm at build · accent-emphasis `oklch(0.58 0.10 58)` — lower chroma than A's,
  expect ≥4.5:1 white-on-it, confirm at build · accent-tint `oklch(0.95 0.02 58)`
- Dark mode: substrate `oklch(0.16 0.004 58)` · text `oklch(0.93 0.005 58)` · accent-dark
  `oklch(0.70 0.08 58)` (verify at build)
- Status vocabulary rendered as "plotted-fix" ring markers, not chips — same canonical five
  states, different grammar than A: thin solid ring = confirmed/posted (green H≈145°); dashed
  ring = pending/estimate (blue-gray H≈240°); heavy ring = error/overdue (red H≈25°); hollow gray
  ring = draft; filled dark ring = closed.
- Focus ring: 2px solid accent-ink, 2px offset, `:focus-visible` only.
- Type: Inter Variable primary (same reason as A, kept as the default pair per row 6). Source
  Serif 4 Variable, self-hosted, reserved ONLY for the marginalia/annotation layer (running-head-
  as-breadcrumb, margin notes) — reason: marks that layer as commentary distinct from the grid's
  data, serving the collision's surface parent directly.
- Scale: role-indexed. Title 20px/600; running-head/margin serif 13px italic/400; body/data
  14px/450 tabular; meta 12px/450.
- Style-under-density: *Swiss/table holds density natively — a table is a grid with the lines
  turned on. The margin column is the risk: at forty rows it cannot carry a note per row, so it
  collapses to the two or three loudest patterns only — dense grid, sparse commentary, per
  STYLES.md's own bimodal-density worked answer.*

### Concept C — press-panel
- Substrate `oklch(0.98 0.002 58)` (coolest/flattest of the three — "brushed steel") · primary
  text `oklch(0.19 0.006 58)` · secondary `oklch(0.44 0.008 58)` · hairline
  `oklch(0.86 0.005 58)` — most desaturated ramp of the three, so the one clay object pops
- Accent-ink `oklch(0.40 0.10 58)` · accent-emphasis (clay button only, richest chroma of the
  three) `oklch(0.60 0.14 58)`, white label — in-family with A's verified 5.06:1 at similar L/C,
  expect close, confirm at build · accent-tint `oklch(0.93 0.035 58)`
- Clay button: large radius (16–20px), layered soft box-shadow pair (light+dark, ONE consistent
  light-source direction held identical in light AND dark mode — per STYLES.md's neumorphism-
  inversion warning: inverting the shadow puts the light source underneath, which no physical
  object does), hard 2px `:focus-visible` ring — never a deeper shadow standing in for focus
  (the required claymorphism accessibility fix).
- Claymorphism confined to exactly two roles system-wide: the primary/confirming CTA button, and
  the "pending/in-progress" status pill. Never on cards, containers, or body chrome. This is the
  literal execution of the human's "used carefully, tastefully, very minimal" instruction.
- Dark mode: substrate `oklch(0.17 0.004 58)` · text `oklch(0.92 0.004 58)` · clay shadow keeps
  its light-direction fixed, only hue/surface retuned.
- Status vocabulary: canonical five states, flat chips for draft/posted/error/closed; pending is
  the one clay-rendered pill.
- Focus ring: 2px solid accent-ink everywhere, including the clay button.
- Type: Inter Variable only — no second family. Reason stated on the line: "a flat panel with one
  dimensional button is a material distinction, not a typographic one; a second face would
  compete with the one thing this direction wants noticed."
- Scale: role-indexed. Title 20px/600; body/data 14px/450 tabular; meta 12px/450; clay-button
  label 15px/600.
- Style-under-density: *data-brutalist is the stricter parent — forty rows is its designed load.
  The gate is the clay role staying confined to one button and one pill per screen; if it migrated
  onto rows, forty soft shadows would stutter the compositor. Confined as specified, cost is flat
  regardless of row count.*

Light/dark declaration: all three are **one design in two palettes**, not two art directions —
none is atmospheric, motion-native, or fully material-heavy (C's claymorphism is bounded to two
roles, not the whole surface, so it does not trigger STYLES.md's two-art-directions rule). C's
clay-button shadow direction is the one element requiring explicit per-mode discipline (light
source held constant across modes), stated above.

## 6–7. Concepts, distinctness tests

Full concept development (collision sentence, opening move, content presentation, navigation,
missing/wrong states, surface list) is written directly into the Gate A package returned in the
final message, to avoid duplicating it here. Screen-flow (identical across all 3 concepts, N=7):
01 login → 02 role home → 03 items list (dense grid) → 04 vendor bill detail (document flow) →
05 new item form → 06 empty state → 07 error state (the CURRENT.md §8 silent-failure bug, fixed
in all three).

**Swap test.** Screen titles: A uses cert/log register ("Item Log," "Bill Certificate"); B stays
plain in titles but shifts in status/empty-state language ("Nothing plotted yet"); C is the
plainest register throughout ("Items," "Vendor Bill"). Empty-state copy, the clearest swap-test
probe: A "No certificate on file. Log the first item to open one." / B "Nothing plotted yet. Log
the first item to start today's chart." / C "Nothing here yet." + one embossed "Log first item"
button. Distinct voices; none of the three reads as a valid swap into another. Passes.

**Family pass.** gauge-house / chart-table / press-panel — three concrete, non-overlapping real-
object nouns. No shared vocabulary, no label that fits two concepts. Passes (fresh-judge half
happens at Gate A, per spec — human matches label to concept before seeing them).

**Category-reflex check.** None of the three are guessable from "surface for an ERP" or "ERP plus
obvious twist" (not "ERP but dark," not "ERP but bento," not "ERP but glassy"). All three trace to
non-obvious physical referents tied directly to the archetype. Passes.

## 8. N and dispatch

Three concepts, seven surfaces, twenty-one coded comps. Coded-comp mode throughout, per dispatch
instruction. Tool-shaped desktop screen canvas: fixed 1440×900 viewport spec, full chrome, real
row counts.

Dispatching 21 surface-designer workers now, one per surface per concept, in parallel.
