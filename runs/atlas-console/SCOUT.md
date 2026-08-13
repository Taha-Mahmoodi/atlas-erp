# SCOUT.md — atlas-console

Return package for the redesign-scout pass. `CURRENT.md` (same directory) is the measurement;
this file is the read on it. Nothing here is taken — the classification below is a proposal for
a human to confirm at the fork, not a decision this pass made.

---

## Positioning read

**No named family from `STYLES.md` fits this cleanly, and it doesn't need to.** This is not a
styled surface reaching for Swiss or Brutalism or any named vocabulary — it is closest in spirit
to `STYLES.md`'s **Monochrome plus one accent** (a tonal ramp carries structure, one accent hue
appears where attention must go) crossed with **Data-brutalist**'s discipline (tabular figures,
hairline rules, real table semantics) — but calling it either by name overstates how deliberate
the *visual* choice was versus how deliberate the *systemic* choice was. What's actually on
screen is a small, strict internal design system executed in Tailwind + OKLCH tokens: one type
family, one accent hue (260°, blue), a neutral ramp hue-locked to that same accent at low chroma
(`CURRENT.md` §2 — the literal "tinted neutral" construction from `STYLES.md`'s ramp-building
section), a two-level heading hierarchy held with zero exceptions across 11 modules, and
right-aligned tabular-figure money columns everywhere money appears. That is **~80–90% one
position, executed with real discipline**, not a template and not driftless — see below.

**Choice or accident — the two checks that can answer it without a human:**

1. **Consistent where nobody enforces it by accident?** Mixed evidence, and the split is
   informative. *Consistent:* the H1 pattern (20px/600, zero exceptions across every page
   sampled, including the catch-all "Unknown module." fallback and a kanban board — a
   structurally different view type from every list/detail/form screen); the tinted-neutral
   ramp; tabular-nums + right-align on every money column sampled; the focus-visible ring
   (2px solid accent, 2px offset — present and correct everywhere tab order was tested); the
   ~36px control height held everywhere (nav, table rows, sign-out) rather than varying by
   screen. *Not consistent:* the status-badge color vocabulary (`CURRENT.md` §7) — the same
   word (`CLOSED`) renders in two different colors in two different modules, and two different
   words (`RECEIVED`, `CLOSED`) share one color within a single module's own list. That is
   exactly the kind of thing that only drifts when nobody wrote the rule down, on a surface
   where everything else shows a rule was written down.
2. **Does the position cost anything?** Yes, specifically: the palette is genuinely held to a
   small set of hue-locked tokens rather than picking up Tailwind's stock gray scale (which
   would have been the zero-cost default), and the control-density choice (36px rows, not the
   more common 40–48px) is paid for everywhere uniformly rather than varying screen to screen.
   A system that refuses the free defaults and pays the same density cost on every screen is
   evidence of an actual decision, not an absence of one.

**Reading:** this is `STYLES.md`'s first row — **~80% of one family with drift** — not the
second (~30% of six families, no position) and not the third (100% of one family unmodified,
a shipped template). The drift is real and concentrated in specific places (status-color
vocabulary, the absence of the nine data states, raw backend text in the one validation message
sampled, the un-collapsing nav at narrow widths) rather than spread evenly across the whole
surface, which is itself informative: an accidental surface drifts everywhere equally; this one
holds its type/color/density discipline everywhere and drops the ball specifically on the
*behavioral* layer — what happens on empty, error, and filtered-empty; what the status
vocabulary means; what a narrow window does.

## Proposed classification: **Correction**

**Evidence.** By `REDESIGN.md` §3's own table: the position is defensible for a tool-shaped
ERP console (dense tables, a held type scale, a real token system, tabular figures on money —
all named wants in `TOOLS.md` §2 and §12) and the measured percentage lands in the ~80%
band with the drift concentrated in specific, nameable spots rather than the position itself
being absent or wrong for the intake. Nothing measured contradicts `TRANSLATE.md` row 1
(tool-shaped, confirmed) or row 6 (Tailwind + self-hosted Inter, confirmed exactly). There is
no evidence of a wrong-for-the-brief position — no glassmorphism on a data-dense console, no
marketing-site spacing scale on an operations table, none of the mismatches `STYLES.md` and
`TOOLS.md` warn about by name. What's broken is execution: unbuilt states, an inconsistent
status vocabulary, a validation message that skipped the copy layer, a shell that never learned
to resize.

**Consequence, stated per the spec:** correction runs `REDESIGN.md` §4's fix ladder (tool-shaped
ordering: tabular/hairline discipline first, density, keyboard completion, the missing data
states, font/palette last, control relocation last-and-gated) against the system already
extracted here, with no new Gate A, under §5's one-fix-one-commit discipline. It does **not**
run Loop 1, and it does not produce a new `DIRECTION.md`. The escalation rule in `REDESIGN.md`
§3 still applies: three rejected fixes on this path is itself a finding, and would mean the
position was wrong all along — but that has not happened, because no fix has been attempted.
This proposal is falsifiable at the gates, not final.

**What would flip this to reposition**, named so the fork is checkable rather than a feeling:
if a human confirms (via the one question below) that the flat two-level heading hierarchy, the
36px-everywhere density, or the absent status-color system were never decided — just never
gotten to — the finding shifts from "a position with drift" to "no position, wearing a defect
list," and `REDESIGN.md` §2's warning about the ~30%-of-six-families reading would apply instead.
Nothing measured here forces that reading, but nothing measured rules it out either; it is
exactly the kind of fact only a human who was in the room can supply.

## Draft survival list — unconfirmed

Per `REDESIGN.md` §3's load-bearing test (what breaks *outside this surface*), drafted from
what's measured, not confirmed with anyone:

- **The Inter Variable self-hosted font file** — already named load-bearing in `TRANSLATE.md`
  row 6, confirmed still in exclusive use on every page sampled.
- **The route structure under each module** (`/inventory/items`, `/finance/vendor-bills/{id}`,
  etc.) — 150+ routes exist; any of them could be bookmarked, scripted against, or referenced in
  internal documentation/training material that this extraction pass has no visibility into.
  Flagged as a category, not confirmed for any specific URL.
- **The canonical terms in `CLAUDE.md`** (`item`, `vendor`, `customer`, `warehouse`, `journal
  entry`) are a project-level lock already, independent of this scout pass, and show up
  correctly in every label sampled (e.g., "Items", not "Products"; "Vendor Bills", not "Supplier
  Invoices"). Worth restating here because a reposition that touches copy has to hold this lock,
  and it is not this scout's to waive.
- **The accent hue (260°, blue) and the OKLCH tinted-neutral system** — this is a real, costly
  decision per the positioning read above, not a default. Whether it is *liked* is a different
  question than whether it is *load-bearing* (`REDESIGN.md` §3's own distinction) — nothing in
  the DOM says whether this blue exists anywhere outside the app (a brand mark, a marketing
  site, printed material). Flagged as plausibly load-bearing, not confirmed.
- **What is explicitly NOT drafted as load-bearing:** the status-badge color-to-word mapping
  (already inconsistent, so there is no single mapping to preserve), the un-collapsing nav
  behavior at narrow widths (reads as unbuilt, not decided), and the raw-validation-text
  behavior (reads as a gap, not a feature anyone would miss).

## The absence sweep — summary

Full detail in `CURRENT.md` §8. Headline: of `TOOLS.md`'s nine data states, only **empty** and
**error** were reachable and neither is designed to spec — empty-after-filter is indistinguishable
from true-empty (no "clear filters" affordance), and the error state for a bad record ID renders
**no error at all**, just a silently-reset blank form with the failure visible only in DevTools.
Five states (loading, partial, permission-denied, offline, stale, conflict, bulk — six, not
counting the two reached) were not reachable through this extraction pass at all; see Limits
below for why. Structural omissions: no custom 404 (a bare fallback string exists instead — not
nothing, not designed either), no skip link, no back-navigation on the one detail flow tested, no
global search, no command palette, no dark mode, despite a route count and daily-use profile that
`TOOLS.md` names as the exact trigger for wanting several of these.

## The one question for the human

**Was the flat two-level heading hierarchy, the uniform ~36px control density, and the absence
of a status-color system each decided, or did the team simply not get to them yet?**

This is the one distinction the DOM cannot make on its own (`REDESIGN.md` §2). Everything else
measured points toward "decided, with drift at the edges" — but "decided" and "never revisited"
render identically in a rendered DOM, and only someone who was in the room for this build knows
which one happened. The answer determines whether the fix ladder in `REDESIGN.md` §4 is the
right next step (correction) or whether this needs to go back through Loop 1 with `CURRENT.md`
as an input constraint (reposition) instead.

## Limits on this measurement

- **No production deployment exists to measure against.** Every performance and LCP number in
  `CURRENT.md` §5 was read on `localhost` against a pre-built bundle with zero network latency —
  it demonstrates the shell *can* be light, not what it actually costs a real operator on a real
  connection. Flag any fix-ladder work that leans on this number for its risk/impact call.
- **Six of the nine `TOOLS.md` data states were not reached.** Loading and partial were not
  forceable without network throttling or a way to fail one widget independently (not available
  through this tooling against a local instance with sub-50ms responses everywhere). Permission
  denied was not reachable with a single-role demo login (`owner` only — no second role to test
  against). Offline, stale, and conflict were not reachable without either offline simulation or
  a second concurrent session, neither available in this pass. Their absence from `CURRENT.md`'s
  findings is an absence of *evidence*, not evidence of absence — a follow-up pass with a second
  test role, a throttled network, and two concurrent sessions would close this gap.
- **Only one narrow-width breakpoint set was tested** (1440/1024/768/390, all on one screen —
  the dashboard). The resize-clipping finding in `CURRENT.md` §10 is confirmed on that one
  screen and cross-checked against `AppShell.tsx` source (no responsive variants on the nav
  container, so the finding generalizes structurally), but no other screen was walked through
  the same four widths individually.
- **No pages behind a second role or a second tenant were reached.** Everything here is the
  `owner` role on the `acme` demo tenant. Role-shaped navigation (`TOOLS.md` §7 — "an operator
  does not see admin sections they cannot use") was not tested at all, because no second-role
  credential was provided.
- **Seed data is small (single digits to low tens of rows per module).** The density and
  forty-rows claims in `STYLES.md`'s "Style under density" section and `TOOLS.md` §2 could not
  be tested at realistic volume — everything measured about row height and table behavior holds
  at 3–12 rows, not at the hundreds or thousands `TOOLS.md` §11 warns is the real production
  case ("the table with 40 rows in development has 4 million in production").
- **The bulk-action and command-palette absences are negative findings from a single session's
  navigation, not an exhaustive audit of all 150+ routes.** It is possible a bulk-select or
  keyboard-shortcut affordance exists on a screen this pass did not visit; the ones sampled
  (inventory items, vendor bills, sales orders, purchase orders, CRM leads, HR leave requests,
  the kanban board) showed none.
- **One conflicting self-report already caught and corrected mid-pass, noted for the record:**
  an early read of the CRM kanban board suggested a "WON"/"LOST" column was clipped with no way
  to reach it; a closer check found a working `overflow-x-auto` container and retracted the
  claim before it reached `CURRENT.md`. Stated here as a discipline note, not a finding — the
  corrected read is what's in `CURRENT.md` §11's screenshot description.
