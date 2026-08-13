# press-panel: Surface 7 of 7 — Error state

Coded comp · tool-shaped desktop screen · fixed 1440×900 viewport · platform mode N/A.

Terminology lock honored throughout: item / vendor / customer / warehouse / journal entry.

Collision: data-brutalist (dominant/structure) × claymorphism (bounded/surface, gated on
restraint — clay confined to exactly two roles system-wide: the primary CTA button, the
"pending" status pill). This surface is the collision's restraint case, not its showcase.

---

## 1. Layout move — the numbers

**Composition anchor: `centered-statement`.** One message block on the vertical *and*
horizontal axis of the content field, everything else (rail, top bar) held to fixed, minimal,
unchanging geometry around it. This is the correct anchor for a screen whose entire content
is one fact and two next actions — a `dense-grid` or `left-rail-caption` anchor would imply
there is more here to look at than there is, which is the opposite of what this surface is
for.

**Background mode: `flat-surface`.** One substrate (`oklch(0.98 0.002 58)`) under rail, top
bar, and content alike. No tint, no gradient, no texture, no image, no danger-red field. Flat
is the content, not just the treatment — see §4 on why the danger token is withheld entirely.

### Grid, in pixels

```
1440 px canvas
├─ left rail        240 px   (fixed, full height)
└─ content field    1200 px  (remainder)

900 px canvas (full height)
├─ top bar (full width, 0–1440)        56 px   sticky, border-bottom hairline
└─ content band (rail + content, 56–900)  844 px
     ├─ top margin       ~280 px   (calculated, not eyeballed — see below)
     ├─ message block     285 px
     └─ bottom margin     ~279 px
```

### Message block (440px column, centered in the 1200px content field)

Content-field center x = 240 + 1200/2 = **840**. Column: x 620–1060 (440px wide), text and
button centered within it — the one internal alignment choice that differs from every other
surface in this concept (rail nav and table surfaces read left-aligned; this one reads
centered, because a single fact has no column to anchor to and forcing one would manufacture
structure that isn't there).

```
y  (32px glyph, centered)                                    h=32
+16
y  ITEM LOOKUP  (eyebrow, 12/600 caps, secondary-text)        h=16
+12
y  "No record found for ITM-4471"  (title, 20/600, primary)  h=28
+12
y  "ITM-4471 doesn't exist in this warehouse's records —
    nothing was saved or lost; there was nothing here to
    begin with."  (body, 14/450, secondary-text, 2 lines)     h=40
+24
y  ── short rule, 48px wide, 1px, hairline-border ──          h=1
+24
y  [ Back to items ]  flat button, 40×~168, centered          h=40
+16
y  "or press  ⌘K  to search again"  (body 14/450 + inline
    12/450 kbd chip)                                          h=24
```

Sum: 32+16+16+12+28+12+40+24+1+24+40+16+24 = **285px**. Centered in the 844px content band:
(844−285)/2 = 279.5 → **280px top margin, 279px bottom margin** (1px rounding remainder, not
a discrepancy). Block spans y=336 to y=621.

### Top bar (56px, full width, sticky)

Left, x=24: "Atlas ERP" wordmark, title role, 20px/600, primary-text — the app identity, not
a page title; the page has no title row of its own on this surface (see "dropped" note below).
Right, ending x=1416: "owner@acme.test" (14px/450, secondary-text) then "Sign out" (14px/450,
accent-ink, 24px gap between the two). No breadcrumb row and no ⌘K search field in the top
bar on this surface — both are real components on sibling surfaces (items-list carries a
320px ⌘K field in its own header) but are deliberately absent here so the ⌘K affordance lives
exactly once, inline in the message block, rather than duplicated top and center.

### Left rail (240px, fixed, full height)

Same substrate as everything else, single 1px right hairline border, no separate fill — the
Swiss/brutalist half of the collision: one material, sections named by position, not by paint.
Nav items, real module names from the build order, 40px row height each (control floor — these
are real controls), 16px horizontal padding, 16px top padding before the first item:

Home · Finance · **Inventory** *(current — accent-ink text, 2px accent-ink left border)* ·
Procurement · Sales · Manufacturing · Quality · Maintenance · HR · Projects · CRM · Reporting
· Admin

13 items × 40px = 520px, leaves 844−16−520 = 308px of unused rail below the list — held empty
on purpose, not filled with a footer or a decoration, matching the surface's own restraint.

### The 32px glyph

A plain outlined square with one diagonal stroke through it — a "record, crossed" mark, not a
red triangle-exclaim and not an illustration. 1.5px stroke, secondary-text color, no fill.
Reads as "this thing isn't here," not "something went wrong."

### The primary button — flat, deliberately not clayed

`Back to items`, 40×~168px (auto width, 20px horizontal padding around 14px/500 label),
2px radius, background `accent-ink oklch(0.40 0.10 58)`, label white, **zero box-shadow, zero
inflated radius, zero inner highlight/bevel** — filled and legible as the primary action
without a single one of the clay tells. See §4 for why: this is the concept's restraint rule
exercised on the exact button role that gets the clay treatment elsewhere in the set.

### The secondary action — inline, not a second button

"or press ⌘K to search again" — 14px/450 secondary-text, with `⌘K` set as a small flat chip
inline (12px/450, 1px hairline border, 2px radius, ~4px horizontal padding, ~20px tall,
baseline-aligned into the 24px row). Not a duplicate button; a text hint pointing at a
mechanism (⌘K) that already exists globally in the app, per the purpose brief.

---

## 2. Type table

| Role | Face | Size | Weight | Line-height | Where |
|---|---|---:|---:|---:|---|
| Title | Inter Variable | 20px | 600 | 28px (1.4) | top-bar wordmark; message heading |
| Eyebrow (comp's own addition) | Inter Variable | 12px caps | 600 | 16px (1.33), +0.04em tracking | "ITEM LOOKUP" |
| Body / data | Inter Variable, tabular-nums | 14px | 450 (button: 500) | 20px (1.43) | body copy, top-bar email/sign-out, secondary-action line |
| Meta | Inter Variable | 12px | 450 | 16px (1.33) | rail nav labels *(14/450 per below — see note)*, ⌘K chip |

Note: rail nav items in this concept's system run at 14px/450 (500 for the current item), same
as the sibling `chart-table` rail convention — the dispatch's "meta 12px/450" role is used here
only for the inline `⌘K` chip and would read too small for a primary-navigation control at the
40px row height above.

---

## 3. Paired colors, with ratios

All ratios below are **computed, not rendered** — via a real OKLab→linear-sRGB→WCAG
relative-luminance script (Björn Ottosson's OKLab matrices, standard sRGB piecewise EOTF),
not estimated.

| Foreground | Background | Computed contrast | Floor | Verdict |
|---|---|---:|---:|---|
| primary text `oklch(0.19 0.006 58)` | substrate `oklch(0.98 0.002 58)` | **17.44:1** | 4.5:1 (body) | pass, wide margin |
| secondary text `oklch(0.44 0.008 58)` | substrate | **7.34:1** | 4.5:1 | pass |
| accent-ink `oklch(0.40 0.10 58)` | substrate | **8.97:1** | 4.5:1 | pass — also clears the ≥7:1 the palette implies elsewhere |
| white `oklch(1.0 0 0)` | accent-ink `oklch(0.40 0.10 58)` (button fill) | **9.50:1** | 4.5:1 | pass, wide margin |
| hairline border `oklch(0.86 0.005 58)` | substrate | **1.45:1** | 3:1 (non-text UI) | below floor — same inherited hairline value as the rest of this palette; used here only as a decorative 48px rule and the rail's separator, never as a required interactive boundary, so not held to the 3:1 floor on this surface (flagged system-wide already by the `gauge-house` login spec) |
| danger `oklch(0.5 0.18 25)` | substrate | 6.22:1 *(computed for reference)* | — | **not used anywhere on this surface** — see §4 |

---

## 4. Content direction — one line

Plain fact, plain fix: name the exact bad ID ("No record found for ITM-4471"), say directly
that nothing was lost because there was nothing to lose, and give one flat button plus one
keyboard hint — no red, no exclamation glyph, no clay on the one button that would get it
anywhere else in this concept, because this surface is where "bad news is never clayed" gets
proven rather than just stated.

**On withholding the danger token:** the concept makes `oklch(0.5 0.18 25)` available
system-wide for real errors (failed validation, a blocked action). A missing record because
of a stale or bad ID is not that — it's informational, not a failure the user caused or a
system fault — so this comp deliberately does not spend the red token here, keeping it
reserved for surfaces that are actually reporting a fault. This is a design decision, not an
oversight, and the reason it's flagged this explicitly rather than silently: a reviewer
scanning for "does the error surface use the error color" would otherwise read the absence as
a miss instead of the choice it is.

---

## 5. Self-check (embarrassment gate)

Read back against the palette table above: all six pairs are accounted for, all six ratios
were run through the script rather than eyeballed, and the one sub-floor pair (hairline,
1.45:1) is flagged with its actual use (decorative rule / separator) rather than presented as
if it cleared 3:1. The one clay-eligible object on this surface (`Back to items`) is
deliberately rendered flat — checked against the concept's own permission clause, which allows
clay here *if* framed as the confirming primary action, and against this surface's explicit
"no clay, no drama" instruction, which wins: zero clay objects on this comp, which is stated
in the concept brief as "fine and correct," not a compromise. No fabricated brand name (Atlas
ERP is the real product name). No invented metric presented as data — the item code
`ITM-4471` is a plausible identifier, not a claim. Four bands N/A (desktop tool-shaped
surface, not mobile). Would put a name on this.

---

## Logged tokens

- **Composition anchor:** `centered-statement`
- **Background mode:** `flat-surface`
- **One line:** the whole surface is one centered block with two fixed, minimal chrome bars
  around it (56px top bar, 240px rail) — the opposite move from the `dense-grid` sibling
  (items-list, where the table *is* the composition) and a genuinely different axis than a
  `stacked-center`/left-aligned form (login): this is the only surface in the set whose
  message text itself is center-aligned rather than left-aligned, which is the deliberate
  signal that there is nothing here to scan, only one thing to read.

## Unsatisfied / flagged

1. **Hairline contrast (1.45:1)** — inherited system-wide from the dispatch palette, not a
   choice made on this surface; same finding the `gauge-house` login spec already raised.
   Used here only for a decorative 48px rule and the rail separator, neither a required
   interactive boundary, so it does not block this surface, but the underlying palette value
   is worth a Loop 1 pass before any surface needs a hairline to double as a real control edge.
2. **No breadcrumb row** — items-list's sibling header carries a 56px breadcrumb ("Inventory /
   Items") plus a 320px ⌘K field; this surface drops both to keep the top bar to identity +
   session controls only, so the centered message reads as the one thing on the page. If a
   real build wants breadcrumb continuity even on a not-found state (so the user can see they
   were inside Inventory → Items before the bad ID hit), that's a real trade-off against this
   comp's "plainest surface in the set" brief, not a free addition.
