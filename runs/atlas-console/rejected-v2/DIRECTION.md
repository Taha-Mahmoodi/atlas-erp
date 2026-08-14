# DIRECTION.md — atlas-console (attempt #2)

Direction half, written by `direction-conductor` (Loop 1). Craft-conductor completes this file at
rendered-style resolution in Loop 2, after Gate A. This is the record, not the gate — Gate A is held
by the session that dispatched this agent.

**Run:** the whole authenticated Atlas ERP app shell (login → AppShell → 11 modules). One surface.
**Attempt:** #2. Attempt #1's three concepts (gauge-house, chart-table, press-panel) were rejected
in full at Gate A — register, not execution. Full record archived at `rejected-v1/`. Nothing in this
file reuses that attempt's structural parents, palette, or reasoning; see `direction-draft.md` §0
for the read on what changed and why.
**Classification:** reposition (unchanged from attempt #1 — human-confirmed override of
redesign-scout's proposed correction). `CURRENT.md` and `SCOUT.md` remain the input constraints.
Survival list honored: Inter Variable self-hosted (kept, both concepts), the `CLAUDE.md`
terminology lock (item / vendor / customer / warehouse / journal entry — held in every comp), the
route structure (untouched). The 260° accent hue is **not** kept, same as attempt #1 — re-derived
fresh this pass, not retuned from either prior number (58° copper or 260° blue). See §5.

---

## 1. Surface class

**tool-shaped**, per `TRANSLATE.md` row 1, confirmed, unchanged. One run for the whole authenticated
shell, not one per module.

## 2. Platform mode

**Skipped, by decision.** Web-only, desktop-only surface — every named role (finance, inventory,
manufacturing, HR, CRM, sales, procurement, projects, quality, maintenance, admin, reporting) is a
desk role under `TOOLS.md` §10's own test, and nothing in `TRANSLATE.md` row 2 or `CURRENT.md`
signals a phone/tablet target. `SURFACES.md` not read (reading-list condition doesn't apply). Named
explicitly as RISK 3 below — this reasoning could be wrong, and the cost if it is wrong is real and
stated there, not assumed away.

## 3. `ACCESS.md` §13 — 19 of 23 rows answered (13 shared + 6 tool-shaped). 4 native rows N/A (no
native target this run).

| # | Decision | Answer |
|---|---|---|
| 1 | Target size route | Primary controls at a real **44px** floor (closes `CURRENT.md`'s measured 36px gap with real margin, not a bare-minimum one). Base spacing unit **8px** enters the scale before type. Dense icon-only row-action clusters (row actions, both concepts' inline status controls) use the WCAG 2.5.8 spacing exception instead: 16–18px glyphs, 8px gaps → 24px centre-to-centre. A density toggle exists per `TOOLS.md` §2; compact mode never drops control height below 40px |
| 2 | Contrast boundary | Web's 18px/14pt-bold "large text" line (3:1); everything under it is body (4.5:1) — not Apple's 17pt; this is web, no native target |
| 3 | Can the sampled accent carry body text / 3:1 graphical / neither | **Accent-ink grade** (L≈0.42–0.44, C≈0.15, H290, both concepts) — body-text legal, estimated ~7–7.2:1 on each concept's light substrate. **Accent-emphasis grade** (L≈0.52–0.53, C≈0.18) — estimated ~4.8–4.9:1 white-on-it: close enough to the 4.5:1 floor that it is named as unverified (§8/RISK 4) rather than assumed safe. **The vivid gradient-CTA endpoint** (the-yard only, C≈0.20–0.22) is 3:1-graphical/large-text-only, explicitly never small body text — stated as a placement constraint, not a footnote |
| 4 | ⑂ Focus indicator, per concept | **the yard:** 2px solid accent-ink ring, 2px offset, `:focus-visible` only; checked against white cards, the tinted substrate, and inside a focused signal-token (ring sits outside the token's own fill so it never merges with the state hue). **lightbox:** same ring spec, plus checked against the glass command bar's translucent background at its worst (busiest-scrolled) frame — the one surface in the run where the ring's backdrop actually moves |
| 5 | ⑂ Sticky chrome geometry, per concept | **the yard:** reserved layout space, not modal — lane-grid header and any sticky table header reserve real space (`space-sticky = 56px`), never floats over content uninvited. **lightbox:** the glass command bar is the run's one sticky element; it is reserved-space **and** carries an opaque scrim behind every text run per the glassmorphism accessibility fix, so it satisfies 2.4.11 by construction (a thin bar, never a full-height panel, so it never entirely obscures a focused element beneath it) |
| 6 | Drag affordance | The one plausible drag surface across both concepts is CRM kanban / lane reordering — not one of the 7 numbered comps this pass. Gets a "Move to…" menu alternative per card, stated as the system rule |
| 7 | Auth path (3.3.8) | Password stays (project's existing architecture, `CLAUDE.md` §4). Paste and password-manager autofill explicitly never blocked in either concept's login comp. No cognitive-test CAPTCHA |
| 8 | Help's fixed slot | One "Help" entry, last item in the left rail, same relative position on every screen, both concepts |
| 9 | Landmark map / heading outline | One `h1` per screen = screen title. One `main`, one `nav` ("Primary"), one `banner`. Skip-to-content link, first in tab order, visible on focus — both concepts (closes `CURRENT.md`'s confirmed-absent skip link) |
| 10 | Accessible names, icon-only controls | Row-action icon clusters get per-record names ("Open BILL-2026-00003," never "Edit" or "More"). the-yard's signal-tokens get names describing state **and** record ("Pending — Bill BILL-2026-00003, due in 2 days"), never a bare color/shape description. lightbox's status dots get the equivalent |
| 11 | ⑂ Reduced-motion still frame | Neither concept is motion-native. **the yard:** skeleton-token loading degrades to instant-visible tokens, no stagger. **lightbox:** the glass bar's blur-in on open degrades to an instant opaque-bordered panel — per `STYLES.md`'s own glassmorphism reduced-motion guidance, never animate into/out of a blur |
| 12 | Script / direction / expansion budget | LTR, Latin script — no RTL/non-Latin signal in the intake. Tightest string checked (`PARTIALLY_DELIVERED`; the-yard's lane labels) sized to content with a stated max-width, not a fixed pixel box |
| 13 | Focus on route change / element removal | SPA route change → focus to the new screen's `h1` (`tabindex="-1"`). Row deleted → focus to next row (previous if last, the table itself if now empty). One answer, both concepts |
| 14 | grid vs table + entered-cell state | Primary work lists (items, vendor bills) are `role="grid"` in both concepts — arrow/Enter/Space/Shift contract stated. Inline status-select (the-yard's token, lightbox's dot) triggers the same entered-cell state: Enter switches to widget-editing, Escape restores grid navigation |
| 15 | Combobox popup role | Item/vendor/customer reference-picker uses `listbox` in both concepts — flat option list, no hierarchy |
| 16 | Modal initial focus + fallback | Confirmation modals (void/approve on vendor-bill detail) set initial focus on the least-destructive action (Cancel). Invoker-gone fallback: focus to next row, or the table itself if empty. Both concepts |
| 17 | Genuinely a menu/menubar? | No — both concepts' left rails stay a plain `nav`. The one real `menu`: a row's "⋯ more actions" overflow button |
| 18 | Live-region triage | Silent: hover previews, the-yard's token-hover reveal, lightbox's glass blur-in. Advisory (`status`/polite): "Saved," filtered-count changes, the-yard's lane counts updating. Imperative (`alert`/assertive): session-expiry, a failed save without preserved input, conflict-detected — conflict also moves focus directly to the conflict panel as a second channel, per `ACCESS.md` §7's finding that `assertive` is unreliable in JAWS/Orca/TalkBack |
| 19 | ARIA patterns as Gate B cost lines | `grid` (full keyboard contract + focus mgmt), `listbox` combobox (`aria-expanded` sync), modal dialog (focus trap + return), overflow `menu` (Tab-exits-widget), `status`/`alert` live regions. Five patterns, shared across both concepts, each traced to an actual comp. lightbox's command-bar search reuses the same `listbox` combobox pattern rather than adding a sixth |

Native rows 20–23: **N/A — no native target this run.**

No row deferred; no cost table needed for this section.

## 4. The derivation

Archetype (`TRANSLATE.md` row 4): **precise, rigorous, honest about its own limits.** Shadow:
**sterile, cold, spreadsheet-generic.** Read this pass against the corrected register: rounded
corners throughout, confident varied hue, real soft depth, glass gated hard on restraint —
contemporary SaaS product, not technical instrument panel (`TRANSLATE.md`'s own read across the nine
supplied references, verified by direct inspection of all nine — full notes in `direction-draft.md`
§0).

**Physical referents derived from the archetype words** (`STYLES.md`'s derive-don't-pick procedure):

1. A harbor/rail dispatcher's magnetic status board — one lane per line, a round colored token slid
   into a car's slot, legible from across the yard.
2. An optician's/watchmaker's fitted case — a felt tray with a cut outline traced for every
   instrument, so an empty groove is exactly as visible as a filled one.
3. A cartographer's light table — the drawing stays flat, opaque, fully legible from directly above;
   the only thing that ever floats above it is a sheet of vellum carrying today's marks.

None reached for Swiss-grid or Terminal by reflex, none recycle attempt #1's data-brutalist,
blueprint, editorial-marginalia, or claymorphism parents. Picked against the five inputs in
`STYLES.md` "Picking one" (category cluster / empty position / anti-positioning / risk appetite /
what's owned) — full reasoning in `direction-draft.md` §3.

**Two directions survive and were developed into concepts (§6–7 below). One — referent 2, "the
tray" — was derived and then cut before development, for cost and fit reasons stated in full at §5
of `direction-draft.md` (reproduced short-form under "Rejected concept" below), per
`loops/01-direction.md` §7's requirement to show the range, not only the survivors.**

## 5. The sampled accent — no existing brand, re-derived fresh

`PRINCIPLES.md` §6's no-brand path applies: no logo, favicon, or brand mark anywhere in the repo —
confirmed again this pass. `TRANSLATE.md` row 6's correction is explicit that Loop 1 re-samples and
decides fresh rather than trusting `CURRENT.md`'s measured 260°-blue table; the rejected 58° copper
is treated as if no accent had ever been proposed. One sampled accent for the whole run, per `§6`
("there is one logo"); both concepts reconcile against it at different lightness/chroma/substrate.

**Physical scene forcing the choice:** *the blue-violet ink of a notary's certifying stamp, chosen
because it cannot be faked by a black-and-white photocopy, pressed fresh onto a page that has just
been checked and is now provably true.* Hue ≈ **290°** — past `STYLES.md`'s 270° "sky blue" anchor,
into violet; deliberately distinct from both the app's existing 260° blue (the ERP category's own
default, and the named benchmark SAP Fiori's color — reaching for it again would be the reflex this
run exists to route around) and the rejected 58° copper. The gradient CTA in reference image 8
(purple-to-blue) sits in the same family, which is corroborating evidence from the supplied
references, not an invented coincidence.

Reconciled against row 3 ("different — not the usual bland and dry ERP") and the corrected row 5
read (confident, varied, not one quiet accent): used at real chroma in both concepts, never
desaturated into a muted retreat.

**Contrast — estimated, not script-computed. Named as the least-verified numbers in this package
(RISK 4 below; §8's disclosure).** No Bash access this dispatch; the usual OKLab→linear-sRGB→WCAG
script pass did not run. Estimated from established OKLCH/sRGB correspondence for this hue family:

- Accent-ink `oklch(0.42–0.44 0.15 290)` on each concept's light substrate: **≈7–7.2:1**, comfortable
  margin, body-legal.
- Accent-emphasis `oklch(0.52–0.53 0.18 290)`, white foreground: **≈4.8–4.9:1** — close to the 4.5:1
  floor. Flagged for a real script pass at Loop 2 before it is trusted for small body text.
- Dark-mode accent `oklch(0.76–0.77 0.13–0.14 290)` on each concept's dark substrate: **≈6–6.5:1**,
  comfortable margin.

## 6. Concept A — "the yard"

**Collision (structural parent named):** Bento (structure) × an invented "signal-token" surface
language — *"A rail yard's dispatch board sorts cars into lanes by where they're going and what's
holding them up, and a rounded colored token slid into a car's slot reads from across the yard;
cross that with bento's own rule that a card's size states its importance, and eleven ERP modules
stop being a flat menu and become lanes sized by how often this operator actually needs them, with
what's stuck in each lane readable at a glance."*

**Opening move:** role-home renders as a bento grid of unequal lanes — one lane per module the
operator's role actually touches (a buyer sees Procurement, Inventory, Sales-demand; a controller
sees Finance, Reporting, Admin), sized by 30-day usage frequency, not alphabetical order. Each lane
carries a metric-display number with its comparison ("↑ 3 from last week" — never a bare number,
per `STYLES.md`'s analytics-cliché fence) and a row of signal-tokens, one per item needing action.
No lane is ever empty of information; a quiet module still shows its steady number in a calm neutral
token.

**Primary content:** real `role="grid"` tables inside each module, tabular figures, decimal-aligned
money, signal-tokens standing in for every status column — shape **and** hue, never color alone
(`§10`). Avatar-chip pattern for any person-attached record. A record detail opens as a right-side
panel holding the document-flow chain (PO→GRN→Bill) as a vertical strip of signal-tokens, one per
stage — matching Atlas's real document-flow architecture (`CLAUDE.md` §"Architecture rules" 2), not
an invented metaphor.

**Navigation:** left rail, icon+label at rest; widens further past 1600px to show a per-item "today"
count badge (reveal, not stretch). ⌘K command palette for go-to/search, reachable globally. Rail
order is role-derived, most-frequent module first, not alphabetical.

**Missing/wrong (`TOOLS.md` nine states):** Empty — a dashed-outline token slot, "No items yet — log
the first one," calm and neutral until the first token exists. Loading — skeleton tokens matching
final layout, never a spinner. Error (the live app's silent bad-ID bug) — a single dark "torn" token
with a visibly broken edge and plain text: "This record wasn't found. Nothing was changed," with a
way back. Permission denied — a grayed, locked token naming who to ask. Conflict — two tokens side by
side, both versions, "keep mine / keep theirs / merge" — `TOOLS.md`'s "show both, let the human
choose," built literally.

**Palette — light:**

| Token | Value | Paired foreground | Est. ratio |
|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | text-primary `oklch(0.21 0.015 290)` | ~15:1 |
| card | `oklch(1 0 0)` | text-primary | ~16:1 |
| text-secondary | `oklch(0.46 0.02 290)` | on card | ~6.5:1 |
| hairline | `oklch(0.89 0.01 290)` | — decorative-only, sub-3:1; never the sole boundary signal |
| accent-ink | `oklch(0.44 0.15 290)` | white / on card | ~7:1 |
| accent-emphasis | `oklch(0.53 0.18 290)` | `oklch(1 0 0)` | ~4.8:1 (unverified — RISK 4) |
| accent-tint | `oklch(0.94 0.035 290)` | accent-ink | ~6:1 |
| gradient CTA (large/graphical only) | `linear-gradient(in oklab, oklch(0.58 0.20 300), oklch(0.52 0.19 255))` | white, bold ≥18px only | 3:1-graphical role, not body |

**Palette — dark:**

| Token | Value | Paired foreground | Est. ratio |
|---|---|---|---|
| substrate | `oklch(0.19 0.012 290)` | text-primary `oklch(0.94 0.008 290)` | ~14:1 |
| card | `oklch(0.24 0.012 290)` | text-primary | ~13:1 |
| text-secondary | `oklch(0.68 0.015 290)` | on card | ~6:1 |
| hairline | `oklch(0.34 0.015 290)` | — decorative-only, same caveat |
| accent-dark | `oklch(0.76 0.14 290)` | on substrate | ~6:1 |
| accent-tint-dark | `oklch(0.30 0.05 290)` | accent-dark | ~5:1 |

Both palettes are **one design in two palettes**, not two art directions — the token mechanism
doesn't change structurally between modes, only lightness/chroma retune.

**Status-token vocabulary** (shape + hue, both required per `§10`; paired per mode):

| State | Hue | Light fill / text | Dark fill / text | Glyph |
|---|---|---|---|---|
| Draft | neutral | `oklch(0.93 0.006 290)` / `oklch(0.4 0.01 290)` | `oklch(0.3 0.01 290)` / `oklch(0.85 0.01 290)` | dashed ring, pencil |
| Pending | 80° | `oklch(0.62 0.14 80)` / `oklch(0.2 0.03 80)` | `oklch(0.7 0.13 80)` / `oklch(0.18 0.02 80)` | clock |
| Posted / Success | 150° | `oklch(0.58 0.15 150)` / `oklch(0.18 0.03 150)` | `oklch(0.68 0.14 150)` / `oklch(0.16 0.02 150)` | check |
| Overdue / Error | 25° | `oklch(0.55 0.19 25)` / white | `oklch(0.65 0.17 25)` / `oklch(0.16 0.02 25)` | exclaim |
| Closed | neutral-dark | `oklch(0.35 0.008 290)` / white | `oklch(0.5 0.01 290)` / white | lock |

**Categorical module hues** (bento lane headers, distinct from the 290° brand accent): rotating
formula `hue = (10 + index × 32) mod 360`, chroma 0.11, L 0.60 light / L 0.68 dark — 11 distinguishable
lane hues across the module set, none landing on 290°.

**Type:** Inter Variable (self-hosted, load-bearing — kept: already owned, full weight axis for the
lane-header/body/mono hierarchy, tabular figures). JetBrains Mono Variable (self-hosted, new) for
document identifiers only — reason: ligature-free monospaced digits keep `BILL-2026-00003`-style
codes scannable at a skim, distinct enough from Inter that an identifier is never mistaken for prose.
Role-indexed scale: metric-display 34px/700 tabular · title 20px/600 · lane-header 15px/600 ·
body/data 14px/450 tabular · meta 12px/450 · mono-identifier 13px/500.

**Style-under-density:** *at forty rows this holds natively on every list screen — a signal-token
is one glyph plus one hue per row, the same cost as a plain badge, so forty rows cost nothing extra.
Only the bento lane HOME surface is exempt from row-count entirely: a lane never tries to enumerate
forty of anything, it holds one number and a handful of tokens for what needs a hand today — density
lives on the list screens, the lanes stay a summary by design.*

**Surfaces (N=7, screen-flow order):** 01 login · 02 role home (bento lanes) · 03 items list (dense
grid) · 04 vendor bill detail (document-flow token strip) · 05 new item form · 06 empty state
(filtered) · 07 error state (bad-ID).

## 7. Concept B — "lightbox"

**Collision (structural parent named):** an opaque, plain data layer (structure, closest to radical
minimalism's discipline — no cards, no shadows, hierarchy from type and space alone) × liquid glass
confined to exactly one object (surface) — *"A cartographer's light table keeps the drawing itself
flat, opaque, and fully legible from directly above; the only thing that ever floats above it is a
sheet of vellum carrying today's marks. Cross that with liquid glass's own rule that it belongs to
the control layer and never the content layer, and the console gets exactly one glass object — a
floating command bar — while every table, form, and record stays flat and fully opaque underneath
it."* This is the literal execution of Taha's own words on row 5 ("glass is back on the table, but
please do it tastefully cuz it is a hard thing to do") — restraint is not a caveat here, it is the
entire structural idea.

**Opening move:** role-home renders as a plain, fully opaque worklist — no cards, no bento, no
color-blocked lanes — grouped "due today / due this week / everything else," single-column reading
order. A translucent, blurred command bar floats fixed at the top (per reference image 6): search,
quick-create, notifications live there, refracting whatever scrolls beneath it. It is the only object
with any blur or transparency on the entire screen.

**Primary content:** real `role="grid"` tables, flat and opaque, tabular figures, decimal alignment,
ordinary hairline rows — no token pills, status renders as small solid-fill dots + a text label
(shape distinct from fill state — solid / outlined / striped / triangle — never color alone).
Selecting a record opens a full detail screen, not a floating panel (panels are for the glass layer
only; a record's detail is content, so it stays opaque and gets its own screen with a back path),
showing the document-flow chain as a plain vertical list with dates and stamps, no ornamentation.

**Navigation:** the floating glass command bar is the primary navigation — press the shortcut, type
a module name or record number, jump there (`TOOLS.md` §3's "search focusable with one key from
anywhere," §7's "search that spans entities and understands identifiers"). A left rail still exists
underneath for discoverability (icon+label, flat, opaque, no blur) — the glass bar is the fast path,
not the only path.

**Missing/wrong:** Empty — one centered flat line of type, "Nothing logged yet. [Log the first
item]" — deliberately the plainest register of the two concepts, because nothing on this surface is
allowed to be decorative. Error (bad-ID) — same restraint: "This record wasn't found. Nothing was
changed. [Back to items]." Loading — flat skeleton matched to the opaque layout, never touching the
glass layer. Permission denied — same plain register, names who to ask. Conflict — two flat opaque
panels side by side, never glassed (a decision worth conflict never gets blurred), with the choose
action.

**Palette — light:**

| Token | Value | Paired foreground | Est. ratio |
|---|---|---|---|
| substrate (opaque data layer) | `oklch(0.99 0.003 290)` | text-primary `oklch(0.20 0.012 290)` | ~16:1 |
| row-alt | `oklch(0.965 0.006 290)` | text-primary | ~15:1 |
| text-secondary | `oklch(0.47 0.015 290)` | on substrate | ~6.3:1 |
| hairline | `oklch(0.90 0.008 290)` | — decorative-only, same caveat as concept A |
| accent-ink | `oklch(0.43 0.15 290)` | on white | ~7.2:1 |
| accent-emphasis | `oklch(0.52 0.18 290)` | white | ~4.9:1 (unverified — RISK 4) |
| accent-tint | `oklch(0.95 0.03 290)` | accent-ink | ~6:1 |
| **glass panel (command bar)** | `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` + `backdrop-filter: blur(20px) saturate(140%)`; border `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)` | text gets its own inner scrim, below | measured against worst-frame — see note |

Glass text scrim: `background: color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)` sits
directly behind every text run on the command bar, per `STYLES.md`'s stated glassmorphism fix,
measured against the busiest table row scrolling beneath it — flagged for build-time re-measurement,
not assumed passing (§8/RISK 1).

**Palette — dark:**

| Token | Value | Paired foreground | Est. ratio |
|---|---|---|---|
| substrate | `oklch(0.155 0.01 290)` | text-primary `oklch(0.95 0.006 290)` | ~15:1 |
| row-alt | `oklch(0.205 0.012 290)` | text-primary | ~13:1 |
| text-secondary | `oklch(0.70 0.014 290)` | on substrate | ~6:1 |
| hairline | `oklch(0.33 0.014 290)` | — decorative-only |
| accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 |
| accent-tint-dark | `oklch(0.28 0.045 290)` | accent-dark | ~5:1 |
| **glass panel (command bar, dark)** | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `backdrop-filter: blur(20px)`; border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)` | same scrim rule, re-measured on dark | — |

**The opaque data layer is one design in two palettes. The glass command bar is two art
directions**, per `STYLES.md`'s own rule for material-heavy families: light mode runs more opaque
and less blurred (60% mix, per the cited "light mode needs more opacity, a heavier border, and less
blur to say the same thing"), dark mode runs less opaque and reads through more (50% mix) — declared
explicitly rather than inverted naively.

**Status vocabulary** (geometric shape + hue, deliberately different grammar from concept A's token-
pills — this is what keeps "component family... stays identical within a concept, differs across
concepts" honest): solid filled circle = posted/success (150°); outlined circle = draft (neutral);
half-filled/striped circle = pending (80°); solid triangle = error/overdue (25°).

**Type:** Inter Variable only (self-hosted, load-bearing, kept) — reason stated on the line: the
opaque/glass material distinction is already the concept's whole statement; a second face would add
a second signal competing with the one distinction that matters here. Role-indexed scale: title
20px/600 · body/data 14px/450 tabular · meta 12px/450 · command-bar-label 14px/500 (same family,
sits on the glass layer, verified against worst-frame per the scrim rule above).

**Style-under-density:** *at forty rows this costs nothing extra: the data layer is fully opaque and
flat by construction, so forty rows are exactly forty ordinary rows, unchanged from four. The glass
command bar is a fixed-size object independent of row count and never touches a row directly —
density and the material risk never meet, which is the concept's own gate working as designed.*

**Surfaces (N=7, same order as concept A):** 01 login · 02 role home · 03 items list · 04 vendor
bill detail · 05 new item form · 06 empty state · 07 error state.

## 8. Rejected concept — "the tray"

Referent: an optician's/watchmaker's felt-lined fitted case — a cut outline traced for every
instrument, so an empty groove is exactly as visible as a filled one. Structural idea: a uniform
(not bento-unequal) modular grid where every possible field/record/module slot always renders —
filled as a solid rounded card, or empty as a dashed ghost outline with a "+" — so nothing is ever
silently missing. The single most direct answer to `CURRENT.md`'s absence-sweep findings and
probably the most "nobody expects this in an ERP" idea of the three derived.

**Why it did not survive the cut to two:** cost, not quality. This pass has two explicit corrective
asks to prove — confident varied color, and a tasteful, restrained glass exploration. "the yard"
proves the first directly; "lightbox" proves the second directly and literally. "the tray"'s core
idea is compelling but visually quiet by construction — absence reads as a calm dashed outline, which
is the whole point — and a quiet, necessarily-restrained grid risks landing closer to the *register*
just rejected (one muted signal, restraint-coded) even though its accent and status hues could still
be built confidently. Given the doubled light/dark cost, it was the direction least load-bearing for
what this specific correction needs demonstrated this pass, so it stops at the derivation stage.

## 9. Distinctness tests

**Swap test.** Empty-state copy, the clearest probe: "the yard" — *"No items yet — log the first
one"* inside a dashed token slot, in the lane's own hue. "lightbox" — *"Nothing logged yet. [Log the
first item]"*, one flat centered line, no color, no shape. Primary-action location differs too: "the
yard" surfaces it inside a lane's metric card; "lightbox" surfaces it via the floating command bar or
a plain button. Neither swaps into the other unreflected. **Passes.**

**Family pass.** Labels: **the yard** / **lightbox** — two concrete, non-overlapping real-object
nouns, no shared vocabulary with each other or with attempt #1's labels. **Passes** (fresh-judge half
happens at Gate A).

**Category-reflex check.** Neither is guessable from "surface for an ERP" or "ERP plus obvious
twist" — not "ERP but bento," not "ERP but glassy," not "ERP but dark." Both trace to specific
physical referents developed into a specific mechanism, not a skin. **Passes.**

## 10. The set-level check

Run once per concept, on the composition anchor and background mode each `surface-designer` worker
logged beside its own comp — read off disk, not out of return messages. **Not self-graded**: 14
independent workers dispatched (2 concepts × 7 surfaces, each producing both light and dark), none
able to see any other worker's output.

**Completed by the orchestrating session, not the dispatched conductor** — the conductor stopped
after all 14 comps were written and `DIRECTION.md` was drafted, before appending this section;
its transcript was not recoverable to resume. Read off disk per spec, not out of any return
message, exactly as the conductor's own instructions require:

| Surface | the-yard anchor / bg | lightbox anchor / bg |
|---|---|---|
| 01 login | `centered-statement` / `flat-surface` | `centered-statement` / `flat-surface` |
| 02 role home | `dense-grid` / `flat-surface` | `left-rail-caption` / `flat-surface` |
| 03 items list | `dense-grid` / `flat-surface` | `dense-grid` / `flat-surface` |
| 04 vendor bill detail | `right-rail-caption` / `flat-surface` | `right-rail-caption` / `flat-surface` |
| 05 new item form | `stacked-center` / `flat-surface` | `stacked-center` / `flat-surface` |
| 06 empty state | `centered-statement` / `flat-surface` | `centered-statement` / `flat-surface` |
| 07 error state | `centered-statement` / `flat-surface` | `centered-statement` / `flat-surface` |

Light/dark pairs match anchor-for-anchor within every surface, both concepts — expected, since
anchor is a layout property that shouldn't flip with palette. **All three anti-repeat criteria
suspended in full**, same carve-out attempt #1 used and for the same reason: this run has no
page-shaped subset, so `flat-surface` dominating every surface and `dense-grid` repeating on
adjacent table-heavy screens is the compliant tool-shaped outcome, not a defect
(`loops/01-direction.md` §10). What a set must *never* vary — checked, not suspended, and
passes: palette/type/component family stay identical within each concept across all 7 surfaces
and both themes (the-yard's signal-token pills + JetBrains Mono identifiers throughout;
lightbox's shape-coded dots + Inter-only throughout), and palette/type genuinely differ across
the two concepts (290°-hue token system vs. 290°-hue opaque-plus-one-glass-object — same
sampled accent, structurally distinct execution, per `PRINCIPLES.md` §6's one-accent rule).

## 11. Coded-comp disclosure

**Ratios computed by estimation, not by script; nothing here has rendered in a browser.** This
dispatch had no Bash access, so the usual OKLab→linear-sRGB→WCAG-luminance script pass did not run —
every contrast figure above is estimated from established OKLCH/sRGB correspondence for hue ≈290°,
not independently re-derived the way attempt #1's 21 workers did. Named as the least-verified part
of this package (RISK 4, Gate A package). First real render, and first script-verified contrast
pass, happens at Loop 2 / build.
