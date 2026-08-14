# direction-draft.md — atlas-console, attempt #2

Working log. Read in full by craft-conductor; also the recovery file if this session dies mid-loop.

---

## 0. What changed since attempt #1

Read `TRANSLATE.md`'s "Gate A — rejected in full, corrected 2026-08-14" section in full, plus the
corrected rows 5/6. All three v1 concepts (gauge-house, chart-table, press-panel) rejected outright
— not execution, the whole register: data-brutalist × {blueprint / editorial-marginalia /
claymorphism-restrained}, sharp/hairline construction, single muted-copper (58°) accent. Taha's
words: "i did not like none of the concepts... the images i uploaded are more of what i envision,
and also the color i did not like the colors you chose."

Read all nine reference images at `runs/atlas-console/references/1.png`–`9.png` directly (not
relying on the summary in TRANSLATE.md). My own read, cross-checked against the corrected section:

1. Endel onboarding — near-black, thin white line-icons, generous whitespace, medium-radius pill
   buttons, restrained. Mood/pacing reference, not a color reference.
2. Light glassmorphic dashboard — frosted white panels layered with real depth via blur radius,
   soft shadows, rounded everywhere. Grayscale mockup so no hue info, but the *material* — glass
   done as a legible layered surface, not a gray smear — is the point.
3. Dark colorful e-commerce dashboard ("Barbara") — near-black substrate, white KPI cards, blue bar
   chart, 5-hue donut chart, multi-color status pills (blue/orange/yellow/green), avatar chips,
   icon-rail sidebar with white active pill. Closest single reference to "confident varied hue."
4. Light SaaS analytics ("Salung") — white substrate, plain sidebar, KPI cards with sparklines,
   status pills (green/amber/gray), bold big numerals, moderate radius, restrained shadow.
5. Dark CRM table ("Sales CRM") — dense table, per-value-colored tag pills (not per-column — each
   tag's own hue), avatar chips, gradient win-probability bars, dense rows with hairline dividers.
6. Light glass context-menu popup — genuinely well-executed glass: large radius, soft shadow, real
   blur with visible bokeh through it, icon+label+kbd-chip rows. The "done tastefully" reference.
7. Light minimal sidebar (Untitled UI) — white, black filled active-pill nav, avatar + shortcut-chip
   profile popup, restrained color, clean spacing.
8. Dark app shell ("Workly") — charcoal substrate, purple-to-blue gradient active nav pill, matching
   gradient CTA button with glow. The one clear "confident gradient" reference.
9. Light blue onboarding ("TrustToken") — white cards, solid blue brand panel, stepper flow, check-
   list rows, QR step. Corporate-but-friendly, moderate radius, restrained trim color.

Read across all nine, my own synthesis matches the corrected section's: rounded corners throughout,
confident/varied hue used deliberately (not decoratively — donut charts, per-value tag hues, gradient
CTAs), real depth via soft shadow and — in exactly two of nine — genuine glass, clean contemporary
SaaS product patterns (pill nav, avatar chips, sparkline KPI cards). Register is "contemporary SaaS
product," not "technical instrument panel." The data-brutalist × blueprint parent I reached for last
time is very likely the wrong family entirely for this correction, not a matter of degree — so I am
not reusing data-brutalist, blueprint, editorial-marginalia, or claymorphism as parents this pass.
Neo-brutalism and cinematic-dark remain flatly banned (`TRANSLATE.md` row 5, `BREAKING.md`'s
never-breakable list). Glass is back on the table, explicitly gated on restraint ("used carefully,
tastefully, and very minimal" / "it's a hard thing to do") — same shape as v1's claymorphism
allowance: a live idea worth *one* concept's real exploration, not a wash over everything.

Read `rejected-v1/DIRECTION.md` in full for what NOT to repeat: the accent hue (58°), the hairline-
as-primary-boundary construction, the "certificate/stamp" and "plotted-fix" surface metaphors, the
data-brutalist structural core in all three. None of it carries forward. What I am keeping from v1
on process grounds only, not content grounds: the N=7 task-keyed surface list (login → role home →
items list → vendor bill detail → new item form → empty state → error state) — it's a genuine
screen-flow tied directly to `CURRENT.md`/`SCOUT.md`'s own findings (the silent bad-ID bug, the
missing empty-vs-filtered-empty distinction), and reusing it gives Taha a comparable review against
what he already looked at once, which is a legitimate reason to hold a structural choice constant
while everything about style, palette, and concept changes underneath it.

## 1. Surface class, platform mode

Unchanged from v1 and from `TRANSLATE.md` rows 1–4, still binding: **tool-shaped**. Platform mode
**skipped by decision** — web/desktop-only, every named role (finance, inventory, manufacturing, HR,
CRM, sales, procurement, projects, quality, maintenance, admin, reporting) is a desk role under
`TOOLS.md` §10's own test, nothing in `TRANSLATE.md` row 2 or `CURRENT.md` signals a phone/tablet
target. `SURFACES.md` not read (reading-list condition doesn't apply). Flagged as RISK 3 below —
this reasoning could be wrong, and the cost of being wrong is real.

## 2. The accent — re-derived from nothing, not from 58° or from 260°

`PRINCIPLES.md` §6 no-brand path applies: no logo, no favicon, no brand mark anywhere in the repo —
confirmed again this pass (`TRANSLATE.md`'s own correction restates it). `CURRENT.md` measured a
real existing accent (`oklch(0.45 0.15 260)`, blue) but `TRANSLATE.md` row 6's correction is explicit:
"Loop 1 re-samples and decides fresh rather than trusting this table" — and the 58° copper this run
proposed instead was rejected outright as a color, full stop, "as if no accent had been proposed
yet." So this is a genuinely fresh deliberate choice, not a retune of either prior number.

Two things it has to avoid by name: the ERP category's own blue-by-convention default (`STYLES.md`'s
own cliché table: "Blue... trust-by-convention," and blue is literally what the app already had, and
what the named functional benchmark SAP Fiori uses) — reaching for blue again is a reflex, not a
choice. And the rejected muted copper — anything read as a single quiet earth tone repeats the exact
mistake just named.

**Physical scene, one sentence:** *the blue-violet ink of a notary's certifying stamp, chosen because
it cannot be faked by a black-and-white photocopy, pressed fresh onto a page that has just been
checked and is now provably true.* This is a real, sourceable fact about certifying stamps (many use
non-photocopiable blue/violet ink specifically to resist forgery) and it ties directly to the
archetype (`TRANSLATE.md` row 4: precise, rigorous, honest about its own limits) rather than being
decorative. Hue ≈ **290°** — past `STYLES.md`'s 270° "sky blue" anchor, into violet, clearly
differentiated from both the existing app's 260° and the rejected 58°. It also happens to sit in the
same family as the one genuinely confident gradient in the reference set (image 8's purple-to-blue
CTA), which is corroborating evidence from the references themselves, not just an invented story.

Reconciled against row 3 ("different — not the usual bland and dry ERP") — it is neither the
category's blue nor a muted retreat, and against the corrected row 5 read (confident, varied, not
one quiet accent) — it is used at real chroma, not desaturated.

One sampled accent for the whole run, per `§6` ("there is one logo"). Both concepts reconcile
against the same H≈290° family; they diverge in lightness/chroma/substrate per direction, which is
the expected divergence `loops/01-direction.md` §5 describes.

## 3. Derivation — physical referents from the archetype, not the family list

Archetype (`TRANSLATE.md` row 4): precise, rigorous, honest about its own limits. Shadow: sterile,
cold, spreadsheet-generic. Read against the corrected register (rounded, confident, soft depth,
glass gated).

Physical/spatial referents considered, each stated as one concrete sentence naming a real object:

1. **A harbor/rail dispatcher's magnetic status board** — one lane per line, a round colored token
   slid into a car's slot, legible from across the yard. Precision = strict lanes; honesty = a
   token's position is only as good as who last moved it, so "last touched" is a visible convention,
   not hidden metadata.
2. **An optician's or watchmaker's fitted case** — a felt tray with a cut outline traced for every
   instrument, so an empty groove is exactly as visible as a filled one. Precision = the case only
   closes if everything is where it belongs; honesty = absence is never invisible.
3. **A cartographer's light table** — the drawing itself stays flat, opaque, fully legible from
   directly above; the only thing that ever floats above it is a sheet of vellum carrying today's
   marks. Precision = the drawing never lies about what's on it; honesty = the overlay is visibly a
   *layer*, never mistaken for the thing itself.

All three are genuinely different physical objects with genuinely different structural logic (unequal
lanes sized by traffic; a uniform grid where absence is the signal; a flat plane with exactly one
translucent layer above it) — none of them is a reflex reach for Swiss-grid or Terminal, none of them
is data-brutalist, blueprint, or claymorphism recycled under a new name.

**Picking, against the five inputs (`STYLES.md` "Picking one"):**

- *Category cluster* — the fence is generic admin templates and the analytics-dashboard cliché
  (3×3 chart-card grid, four big numbers, one chart nobody reads). None of the three referents
  produce that shape by construction.
- *Empty position* — a confident, varied-hue, contemporary-SaaS register is genuinely uncommon in
  enterprise/ERP software specifically (the category cluster here is beige/gray corporate dashboards
  per row 3/5's own cliché fence), so leaning into references 3/4/5/8's energy is the empty position
  *for this category*, even though it's a well-populated register in consumer SaaS generally.
- *Anti-positioning* — glassmorphism gated to restraint (honored: confined to one component family
  in one concept, never a wash); neo-brutalism and cinematic-dark excluded outright from all three
  referents (none of the three reach for either).
- *Risk appetite* — an operator's tolerance is high for anything that removes keystrokes, near zero
  for anything that costs a habit already owned. All three referents keep the keyboard/`role="grid"`
  contract identical; none change how Tab, arrows, Enter, or the primary-action key behave.
- *What's owned* — Inter Variable (self-hosted, load-bearing per `SCOUT.md`'s survival list)
  stays the primary face in every direction; the terminology lock (`item`/`vendor`/`customer`/
  `warehouse`/`journal entry`) holds in every comp; the route structure is untouched.

**Considered and cut before concept development:** referent 2 (the fitted case / "the tray") — kept
through the derivation stage as a genuinely distinct, strong idea (the most direct answer to
`CURRENT.md`'s absence-sweep findings: empty/error states as the design's literal subject), but not
developed into a full concept. See §6 below for the reasoning — this is a cost decision, not a
quality judgment on the idea itself.

## 4. N and the cost decision

Both light and dark are required as real comps this pass, not tokens declared and deferred — Taha's
own words, cost named and accepted: "Both matter equally, full theme support." That doubles the
per-surface cost regardless of comp mode. Coded-comp mode (the default this run, per dispatch) keeps
the *3-concepts* multiplier "nearly flat" per `loops/01-direction.md` §8, but the light/dark doubling
is a separate, real axis on top of that, and it is the one the human was explicitly told to weigh
before accepting.

Given that, and given `loops/01-direction.md` §8's own instruction — "If it is not affordable, cut
to two concepts rather than a partial set... Two complete concepts is a choice. Three partial ones
is a preference dressed as one" — I am cutting to **two concepts**, both fully developed at N=7
surfaces × 2 themes, rather than three concepts at reduced coverage. The third referent (the fitted
case / absence-as-design) is genuinely strong and is recorded in full at §6 below as the rejected
concept, not discarded silently.

**Announcement:** two concepts, seven surfaces, fourteen coded comps per theme — **twenty-eight
coded comps total** (light + dark). Both numbers stated before dispatch, per §8's own requirement.

## 5. The two concepts, developed

See `DIRECTION.md` for the full formal write-up (collision sentence, opening move, primary content,
navigation, missing/wrong states, palette pairs, type, style-under-density). Summary here for the
draft record:

- **"the yard"** — Bento (structural) × an invented "signal-token" surface language (a rounded
  colored token is the one atomic unit for every status anywhere in the system). Role-home is a
  bento grid of unequal lanes, sized by the operator's own 30-day usage, not by module order. Two
  faces: Inter Variable (kept) + JetBrains Mono Variable (new, self-hosted, identifiers only).
- **"lightbox"** — an opaque, plain data layer (closest to radical-minimalism's discipline: no
  cards, no shadows, hierarchy from type and space) × liquid glass confined to exactly one object,
  a floating command/search bar, per Apple's own stated rule that glass belongs to the control layer
  and never the content layer. One face only: Inter Variable — a second face would compete with the
  opaque/glass material distinction that is the whole point.

## 6. The rejected concept — "the tray"

Referent: an optician's/watchmaker's felt-lined fitted case, a cut outline traced for every
instrument so an absence is as visible as a presence. Structural idea: a uniform (not bento-unequal)
modular grid where every possible field/record/module slot always renders — filled as a solid rounded
card, or empty as a dashed ghost outline with a "+" — so nothing is ever silently missing. This is the
single most direct answer to `CURRENT.md`'s absence-sweep findings (no designed empty/error states
today) and probably the most "nobody expects this in an ERP" idea of the three (`PRINCIPLES.md` §2).

**Why it didn't survive the cut to two, specifically:** not quality — cost, and fit to *this pass's*
two explicit corrective asks. This pass has two named things to prove: confident varied color, and a
tasteful, restrained glass exploration. "the yard" proves the first directly (the signal-token/lane
system is built for varied confident hue). "lightbox" proves the second directly (glass confined to
exactly one component, executing Taha's own restraint instruction literally). "the tray"'s core idea
— a uniform grid of ghost-outline slots — is compelling but visually quiet by construction (the whole
point is that absence reads as a calm dashed outline, not a loud one), and a quiet, mostly-monochrome-
by-necessity grid risks landing closer to the *register* Taha just rejected (restraint-coded, one
muted signal) even though its accent and status hues could still be built confidently. Given the
doubled cost from light/dark, it was the direction least load-bearing for what this specific
correction needs demonstrated, so it is the one left at the derivation stage rather than built out.
Recorded in full here per `loops/01-direction.md` §7's requirement to show the range, not only the
survivors.

## 7. Distinctness tests — run on the two developed concepts

**Swap test.** Screen title register: "the yard" titles read as location/traffic language implicitly
(lanes, tokens); "lightbox" titles stay plain and the command bar carries the register instead.
Clearest probe, empty-state copy: "the yard" — *"No items yet — log the first one"* rendered inside a
dashed token slot, in the lane's own hue. "lightbox" — *"Nothing logged yet. [Log the first item]"*,
one flat centered line, no color, no shape. Primary-action label: "the yard" surfaces the action
inside a lane's metric card; "lightbox" surfaces it only via the floating command bar or a plain
button — different location, different register. Neither swaps into the other unreflected. **Passes.**

**Family pass.** Labels: **the yard** / **lightbox**. Two concrete, non-overlapping real-object nouns,
no shared vocabulary, no fixed catalog (not reusing "gauge-house/chart-table/press-panel"'s
vocabulary either). **Passes** (fresh-judge half happens at Gate A, not here).

**Category-reflex check.** Neither is guessable from "surface for an ERP" or "ERP plus obvious twist"
— not "ERP but bento," not "ERP but glassy," not "ERP but dark." Both trace to specific physical
referents tied to the archetype, developed into a specific mechanism (signal-tokens; opaque-plus-one-
glass-object), not a skin. **Passes.**

## 8. What I could not do — said plainly, not buried

- **No Bash access this run.** The direction-conductor's own frontmatter lists `Bash` as an owned
  tool for exactly two jobs: the `date` ledger reading at each phase boundary, and verifying the
  self-hosted font files' actual weights by advance-width comparison. Neither happened — the runtime
  tool list available to me this dispatch was Read/Write/Agent only. The phase-boundary clock is not
  in this record. The Inter Variable and JetBrains Mono Variable weight claims below are stated as
  intended, not verified against the actual `.woff2` files' advance widths.
- **Every contrast ratio in this package is estimated from established OKLCH/sRGB correspondence for
  this hue family, not computed by script.** v1's own run had a conductor plus 21 independent workers
  all re-deriving the math with real computation, which is how it caught two directions' emphasis
  grades falling short of 4.5:1. This run has no equivalent independent verification pass built in by
  default — flagged as RISK 4 in the package, and the accent-emphasis pair specifically (~4.8–4.9:1
  estimated, close to the floor) is named as the first thing to re-check with a real script at
  Loop 2.
- **No live-app re-visit this pass.** `CURRENT.md`/`SCOUT.md`'s own extraction is thorough and recent
  (pixel-sampled OKLCH tokens, not guessed) and row 6's correction explicitly asks for a fresh
  decision rather than trusting the table for the *accent* — which happened (§2 above) — but I did
  not re-open `localhost:5173` myself this pass; there was nothing left to extract that `CURRENT.md`
  hadn't already measured, and re-deriving the accent doesn't require re-visiting the live app when
  there is no logo to sample from it.
