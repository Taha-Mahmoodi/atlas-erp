# chart-table: Surface 7 of 7 — Error state

**Canvas:** 1440×900 fixed viewport, tool-shaped desktop, full chrome.
**Composition anchor:** `right-rail-caption`
**Background mode:** `textured-surface`

Fixes CURRENT.md §8's silent-failure bug: navigating to edit a nonexistent
item (bad ID → backend `422`) currently renders a blank "Edit item" form
with the error visible only in the browser console. This comp is the
designed replacement — the record's expected position on today's chart,
marked as unfound rather than hidden.

## Layout move

The canvas splits into a wide left field (the chart) and a narrow right
rail (the margin), meeting at a hairline rule — the collision drawn as
literal geography: the grid's machine order fills the field, the human
correction sits in the margin beside it, not inside it.

```
0,0 ──────────────────────────────────────────────────────── 1440,0
│ STICKY HEADER — reserved, 0–48px, never overlapped          │ h=48
│ "Items › ITM-4471" (serif italic, x=32)   "AS OF 14:32"(x=1408,←)│
├──────────────────────────────────────────────────────────┤ y=48
│  LEFT FIELD — x 32–1016 (w=984)   │g│  RIGHT RAIL — x 1048–1408 (w=360) │
│                                     │u│                                  │
│  y=80  Edit item — ITM-4471  20/600│t│                                  │
│  +24                                │t│                                  │
│  y=132 TODAY'S CHART · POSTED FIXES│e│                                  │
│        meta 12/450, tracked         │r│                                  │
│  +40                                │  1px hairline rule, x=1048,        │
│  y=188 ── plotting field, h=632 ── │  full height 48–900                 │
│                                     │                                    │
│    08  09  10  11  12  13  14  15  16  17  18   ← hour ticks, meta 12   │
│    |   |   |   |   |   |   |   |   |   |   |                            │
│  ──┼───┼───┼───┼───┼───┼───┼◎──┼───┼───┼───┼──  axis, y=504, 1px       │
│                            ╱ ╲          ITM-4471  body/data 14, y=468   │
│                          ╱     ╲        (above ring)                    │
│                        ╱  (◎)   ╲       y=440  ▪ tie-glyph 8×8,        │
│                      ╱   32⌀,4pt  ╲            error color              │
│                    ╱   heavy ring    ╲  +16                             │
│                   dashed bearing lines  y=464  "No record found for    │
│                   converging on fix, y=640     ITM-4471 — nothing was  │
│                                                 lost, there was nothing │
│           NO FIX — RECORD NOT FOUND            here to begin with."    │
│           meta 12/450, error color, y=548      Source Serif 4 Var,     │
│                                                 italic 13/400, 3 lines, │
│  y=820 ── closing hairline rule, full field ── accent-ink color        │
│  y=820–868 margin, held empty                  +32                     │
│                                                 y=556 [Back to items]   │
│                                                 outline btn 312×40,     │
│                                                 accent-ink border+label │
│                                                 +12                     │
│                                                 y=608 "or press ⌘K to  │
│                                                 search again" meta 12  │
│                                                 ↓ held empty, y 624–852│
│                                                 y=852 "internal ref:   │
│                                                 422 · GET /items/      │
│                                                 ITM-4471" meta 12,     │
│                                                 secondary-text, small  │
└──────────────────────────────────────────────────────────┘ y=900
```

**The ring, precisely.** 32px diameter, 4px stroke, `oklch(0.5 0.18 25)`
[error/danger token, given] — hollow, except a 6px filled dot at dead
center in `accent-emphasis` `oklch(0.58 0.10 58)`: the "fix" mark itself,
the point a chart position gets pencilled once checked. Two 1px dashed
hairline lines run from (≈580,640) and (≈770,640) up to the ring's center
at (≈675,504) — bearing lines converging on a fix, structural grammar,
not commentary. The ring sits under the 14:32 tick, aligned to the header's
own "AS OF" stamp: the record was reached for *right now*, not at some
unrelated hour.

**Why the axis is otherwise empty.** This is a dedicated error surface, not
an embedded chart — it does not borrow other items' real fixes to fill the
frame. One marker, one hour, everything else held blank on purpose: the
same honest-emptiness the concept's empty-state sibling (06) already
commits to, applied here to a single missing point instead of a whole list.

**Rail alignment.** The margin note's tie-glyph sits at y=440, ~64px above
the ring's own y=504 center — high enough that the note block's vertical
mid-point (≈490) lands close to the ring, the editorial convention of a
note hanging beside the line it annotates rather than centered on the
whole rail.

**Control floor.** The one interactive control on this surface — "Back to
items" — is 312×40, holding the 40px floor the concept's login sibling (01)
already set for primary controls. Header is reserved at 48px, distinct
from and taller than that floor, matching the same sticky-chrome decision.
⌘K is a global affordance already established across the app (per
direction-draft's picking-one-check), not invented for this surface — the
rail names it rather than duplicating its UI.

## Type table

| Level | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| title ("Edit item — ITM-4471") | Inter Variable | 20px | 600 | 28px (1.4) |
| margin serif (rail note, header breadcrumb) | Source Serif 4 Variable | 13px italic | 400 | 20px (1.54) |
| body/data (item-ref label, button label) | Inter Variable, tabular-nums | 14px | 450 (button: 500) | 20px (1.43) |
| meta (eyebrow, hour ticks, AS OF stamp, "NO FIX" label, ⌘K hint, internal ref) | Inter Variable | 12px | 450 | 16px (1.33) |

Four levels only, per the dispatch's own role-indexed scale for this
concept — no eyebrow or mono-identifier face invented beyond it (unlike
concept A's scale, this one doesn't carry one, so this comp doesn't add
one either). The header breadcrumb reuses the margin-serif face rather
than Inter: direction-draft names this "running-head-as-breadcrumb"
explicitly — the wayfinding line is voiced as commentary, the "AS OF"
timestamp beside it stays in Inter meta because it's a data stamp, not a
human aside. Line-heights are this comp's own layout decision, as the
dispatch's scale specifies size/weight only.

## Paired colors, at used size

Computed fresh for this surface's exact palette values (OKLCh → OKLab →
linear sRGB → WCAG relative luminance; all pairs confirmed in-gamut).

| Pair | Where used | Ratio |
|---|---|---|
| primary text `oklch(0.22 0.008 58)` on substrate `oklch(0.99 0.002 58)` | title, item-ref label above ring | 16.84:1 *(computed, not rendered)* |
| secondary text `oklch(0.46 0.01 58)` on substrate | AS OF stamp, eyebrow label, hour ticks, ⌘K hint, internal ref line | 6.94:1 *(computed, not rendered)* |
| accent-ink `oklch(0.40 0.07 58)` on substrate | margin note (serif italic), breadcrumb, "Back to items" label + border | 9.14:1 *(computed, not rendered — dispatch expected ≥7:1)* |
| error/danger `oklch(0.5 0.18 25)` on substrate | ring stroke, "NO FIX — RECORD NOT FOUND" label, rail tie-glyph | 6.40:1 *(computed, not rendered)* |
| accent-emphasis `oklch(0.58 0.10 58)` on substrate (non-text, 3:1 floor applies) | ring's center fix-dot only | 4.29:1 *(computed, not rendered)* |
| white on accent-emphasis (text use) | **not used on this surface** — see below | 4.41:1 *(computed, not rendered — falls under the dispatch's own ≥4.5:1 expectation)* |
| hairline border `oklch(0.90 0.006 58)` on substrate | axis line, tick marks, bearing lines, closing rule, rail divider, button border | 1.31:1 *(computed, not rendered — see "couldn't fully satisfy")* |

Focus ring on "Back to items": 2px solid accent-ink, 2px offset,
`:focus-visible` only, per the dispatch's global rule.

## Content direction

Plain register, matching the empty-state sibling's own honest-emptiness
voice rather than gauge-house's certificate-register or an apologetic
error tone: "No record found for ITM-4471 — nothing was lost, there was
nothing here to begin with." reads as the same family as "Nothing plotted
yet. Log the first item to start today's chart." — the concept doesn't
change vocabulary between an empty list and a missing record, it treats
both as the chart honestly reporting what it does and doesn't have. The
technical `422`/route is surfaced, but demoted to a small secondary-text
line at the rail's foot — visible on request, not shouted, which is the
actual fix to the bug (currently that information exists only in the
browser console).

## Self-check (embarrassment gate)

Read back against the palette table above: seven pairs listed, all seven
accounted for on this surface, the two "expect ≥" dispatch values are
quoted as dispatch expectations and checked against the fresh computation
(accent-ink clears its ≥7:1 at 9.14:1; accent-emphasis white-text does
*not* clear its ≥4.5:1 at 4.41:1, and the design was changed — outline
button, not filled — specifically because of that number, not after the
fact). Ring uses shape (heavy stroke) + color + text label together, never
color alone. The one control holds the 40px floor; header holds 48px
reserved. No fabricated brand name, no invented logo, no generated face.
Item ID follows the codebase's real `ITM-` prefix convention (CURRENT.md's
own `ITM-BOLT` example) rather than a random string. Copy length is a
single sentence plus a two-word button — nothing padded to fill the rail.
Would put a name on this.

## Composition and background — one line

`right-rail-caption` because the collision *is* the geography here — wide
field for the grid's machine-checked axis, narrow rail for the one
human-voiced correction beside it, never inside it; `textured-surface`
because the plotting field reads as chart paper (a faint ruled mesh behind
the axis, not an image), which is the concept's own material, not a
decorative overlay.

## Couldn't fully satisfy

1. **Hairline border, 1.31:1 on substrate** — under the WCAG 1.4.11 3:1
   non-text floor. This is an inherited dispatch-palette value, not a
   choice made here, but it's more load-bearing on this surface than
   most: the axis line, tick marks, bearing lines, and rail divider *are*
   the grid half of this concept's collision, and all of them use this
   token. Gauge-house's login (01) flagged the same ramp at a nearly
   identical ratio (1.38:1) — worth a Loop 1 palette check before either
   ships past Gate A, since it now reads as a systemic value across the
   shared ramp rather than a one-surface issue.
2. **White-on-accent-emphasis, 4.41:1** — just under the dispatch's own
   stated ≥4.5:1 expectation for that pair. Worked around by keeping
   "Back to items" as an accent-ink outline button (9.14:1) rather than a
   filled emphasis button with white text, and confining accent-emphasis
   to the ring's small non-text center dot (4.29:1 against substrate,
   clears the 3:1 non-text floor with room). Flagging rather than quietly
   avoiding it, since the dispatch palette states this pair as usable.
3. **"ITM-4471" is comp-invented.** The dispatch's own copy uses the
   placeholder "ITM-XXXX"; no real seed-data ID was available to this
   worker, so a plausible-format value was substituted throughout,
   following the codebase's real `ITM-` prefix rather than inventing a
   new one.
