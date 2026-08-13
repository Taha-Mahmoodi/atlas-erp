# press-panel: Surface 2 of 7 — Role home

**Canvas:** 1440×900 fixed viewport, tool-shaped desktop, full chrome.
**Composition anchor:** `dense-grid`
**Background mode:** `flat-surface`

Login (sibling 01) sits `stacked-center` on a `textured-surface` — a calm,
centered blank field. This is the first busy surface in the set: the
worklist itself takes the visual majority and every other element is
subordinate chrome around it, which is exactly what `dense-grid` names.
Background drops the login's low-contrast blueprint texture entirely — the
opening-move brief calls for "the flattest surface in the set," so texture
is spent nowhere on this screen; the only thing with any visual weight at
all is the one clay button.

## Layout move

```
0,0 ─────────────────────────────────────────────────────────────── 1440,0
│ STICKY HEADER — reserved, 0–48px, full width, never overlapped        │ h=48
│ "PRESS-PANEL · ACME"(eyebrow,x=24)  [⌘K search, 320×40, x=560–880]   │
│                                    "AS OF 9:02 AM"(meta) (FM)(28⌀ av)│
├────┬──────────────────────────────────────────────────────────────┤ y=48
│RAIL│  CONTENT — x 64–1440 (w=1376), y 48–900 (h=852)                │
│x0- │  inner padding 32px → x 96–1408 (w=1312)                       │
│64  │                                                                  │
│icon│  y=72  "Finance Manager"  title 20/600            h=28          │
│-   │        "40 items in today's worklist — 6 need     meta 12/450  │
│only│         approval before the 9:30 cutoff"           h=16, +4gap  │
│rail│  (row h=48, y72–120)                                            │
│    │  +20 gap → y=140                                                │
│40× │  ┌─ CASH STRIP (h=56, y140–196), 3 flat clusters, no card ────┐│
│40  │  │ CASH ON HAND      DUE WITHIN 7 DAYS      OVERDUE            ││
│btns│  │ $184,206.40   │   $42,880.00        │    $6,140.00          ││
│,   │  │ (1px hairline vertical rules at the two internal joins)     ││
│12px│  └───────────────────────────────────────────────────────────┘│
│gap │  +20 gap, 1px hairline full-width rule, +16 gap → y=233        │
│,   │  ┌─ ACTION STRIP (h=72, y233–305), flat substrate, no card ───┐│
│top-│  │ "6 vendor bills need approval        [ APPROVE 6 PENDING  │││
│pad │  │  before the 9:30 cutoff"               VENDOR BILLS ]      │││
│16  │  │ "$18,420.00 total · 3 over 15         280×56, clay, x=1128 │││
│    │  │  days old"  (2-line text block,        –1408, y=249–305    │││
│icon│  │  x96, vertically centered)              (centered in strip)│││
│1:  │  └───────────────────────────────────────────────────────────┘│
│Home│  +24 gap, 1px hairline rule (section divider), +16 gap → y=346│
│▪   │  ┌─ WORKLIST COLUMN HEADER (h=28, y346–374, 1px bottom rule) ─┐│
│2:  │  │ TYPE  REFERENCE  VENDOR/DESCRIPTION  AMOUNT  AGING  STATUS ││
│Items│ │                                                    ACTION ││
│3:  │  └───────────────────────────────────────────────────────────┘│
│Vend│  ┌─ WORKLIST ROWS — scrollable region, y374–876 (h=502) ──────┐│
│ors │  │ 32px row height × 40 rows (1280px total scroll content);   ││
│4:  │  │ 15 full rows + 1 clipped row visible without scrolling —   ││
│Cust│  │ the clip is the "there's more" cue, no "view all" chrome   ││
│omer│  │ needed. Each row: 1px hairline bottom border only (the     ││
│s   │  │ "engraved" line), no fill, no zebra, no shadow.             ││
│5:  │  └───────────────────────────────────────────────────────────┘│
│Ware│  +24 bottom pad → y=900                                        │
│hous│                                                                  │
│e   │                                                                  │
│6:  │                                                                  │
│Jour│                                                                  │
│nal │                                                                  │
│Entr│                                                                  │
│ies │                                                                  │
└────┴──────────────────────────────────────────────────────────────┘ y=900
```

### Header (y 0–48, full width, reserved, sticky)

Left: `PRESS-PANEL · ACME` eyebrow, 12/600 caps, x=24, vertically centered.
Center: ⌘K search, 320×40 (meets the 40px control floor), flat 1px hairline
border, 2px radius, placeholder `"⌘K — search items, vendors, journal
entries…"`, x centered (560–880). Right: `AS OF 9:02 AM` meta 12/450, then
a 28⌀ flat outline avatar circle with initials `FM` (Finance Manager — no
photo; §14 rules out a generated face and there's no supplied one), x
ending at 1408.

### Rail (x 0–64, y 48–900, icon-only at rest)

64px wide, 1px hairline right border separating it from content — the only
vertical divider on the screen. Six icons, 40×40 each (control floor), 12px
vertical gaps, 16px top padding: **Home** (active — active state marked
with a 2px accent-ink left-edge tick, not a fill or a clay treatment),
**Items**, **Vendors**, **Customers**, **Warehouse**, **Journal Entries** —
the five locked nouns plus Home. Labels appear only on `:focus-visible` /
`:hover`, sliding the rail to 200px with a 14/450 label beside each icon;
at rest it's icons only. Rail content totals 300px, top-aligned; the
remaining ~536px of rail height is bare substrate, unfilled on purpose —
the flat-panel ethos doesn't pad chrome to fill space.

### Cash position strip (y 140–196, h=56)

Three flat clusters, no card, no border around the whole strip — divided
only by two 1px hairline vertical rules at the internal joins. Each
cluster: 12/450 secondary-text label, 4px gap, 20/600 tabular-nums
primary-text value. Purely informational, no interactive element.

### Action strip — the one clay object (y 233–305, h=72)

Flat substrate background, same as the rest of the panel — this is not a
card, it has no border, no fill distinct from the page, and no shadow of
its own. It holds exactly one raised object:

**The clay button** — `Approve 6 pending vendor bills`
- **Size:** 280×56px, x=1128–1408, y=249–305 (vertically centered in the
  72px strip)
- **Radius:** 18px
- **Fill:** `oklch(0.60 0.14 58)` (accent-emphasis)
- **Label:** white, 15px/600, centered
- **Shadow stack** (light source: top-left, fixed, both modes):
  1. Ambient contact shadow: `0px 6px 12px 0px oklch(0.60 0.14 58 / 0.30)`
     — a warm, colored shadow (not neutral grey), grounding the button
     against the flat substrate
  2. Top-edge highlight (inset): `inset 0px 1.5px 0px 0px oklch(1 0 0 / 0.35)`
     — the light catch on the raised bevel
  3. Lower-edge depth (inset): `inset 0px -2px 3px 0px oklch(0.40 0.10 58 / 0.25)`
     (accent-ink tinted) — gives the object thickness rather than a flat fill
- **`:focus-visible`:** 2px solid `oklch(0.40 0.10 58)` (accent-ink), 2px
  offset — an added ring, never a substitute for the shadow stack
- **`:active`:** shadow 1 reduces to `0px 2px 4px`, shadow 2 removed —
  the button visibly compresses into the substrate on press

Left of the button, vertically centered: two-line flat text block (no
border, no background) — `"6 vendor bills need approval before the 9:30
cutoff"` body 14/450, then `"$18,420.00 total · 3 over 15 days old"` meta
12/450 secondary-text. This is the only place on the screen the eye is
told, in words, why the one dimensional object exists.

**No other button on this screen — including the 40 per-row "Review"
actions below — takes any part of this shadow stack, this radius, or this
fill color.** That is the whole argument of the surface.

### Worklist column header (y 346–374, h=28, 1px bottom hairline)

12/600 caps secondary-text, +0.04em tracking. Columns (x are absolute,
inner content band is 96–1408):

| Column | x start | width | align |
|---|---|---|---|
| TYPE | 96 | 80 | left |
| REFERENCE | 192 | 110 | left |
| VENDOR / DESCRIPTION | 318 | 576 | left |
| AMOUNT | 910 | 120 | right |
| AGING | 1046 | 90 | left |
| STATUS | 1152 | 130 | left |
| ACTION | 1298 | 110 | right |

16px gutter between every column; 96 + 80+16+110+16+576+16+120+16+90+16+130+16+110 = 1408, the inner right edge exactly.

### Worklist rows (y 374–876, h=502, scrollable region)

32px row height, 14/450 tabular-nums body text, 1px hairline bottom border
per row (the "engraved" line — a plain hairline border, no inset shadow,
no blur; shadows are spent entirely on the one clay button per the
restraint rule, so "engraved" here is a material description, not a second
rendering technique). No zebra fill, no row background change on hover
beyond the border. 502px of visible region shows 15 full rows plus one row
clipped at the bottom edge — that clip is the scroll affordance; the
underlying list is 40 rows / 1280px tall, `overflow-y: auto` within the
bounded region, nothing below y=900 is ever painted outside it.

**40 rows, four doc-type groups** (real counts, representative rows shown;
remaining rows in each group follow the same column pattern):

*Vendor Bill — Pending approval (6 rows, the exact set the clay button
resolves):*
| TYPE | REFERENCE | VENDOR | AMOUNT | AGING | STATUS | |
|---|---|---|---|---|---|---|
| Vendor Bill | VB-04421 | Meridian Office Supply | $3,180.00 | Due in 2d | `Pending` | Review |
| Vendor Bill | VB-04418 | Torrance Freight Co. | $6,920.00 | Due in 2d | `Pending` | Review |
*(+4 more, same pattern)*

*Vendor Bill — Overdue, already approved (9 rows):*
| Vendor Bill | VB-04390 | Whitfield Packaging | $1,240.00 | 11d overdue | `Overdue` | Review |
| Vendor Bill | VB-04382 | Coastal Machining | $8,760.00 | 22d overdue | `Overdue` | Review |
*(+7 more)*

*Journal Entry — Draft, unposted before period close (15 rows; the
VENDOR/DESCRIPTION column carries a memo instead, since a journal entry
has no vendor):*
| Journal Entry | JE-01188 | Accrued freight — Nov close | $14,500.00 | Period closes 3d | `Draft` | Review |
| Journal Entry | JE-01179 | Payroll clearing — reclass | $920.00 | Period closes 3d | `Draft` | Review |
*(+13 more)*

*Customer Payment — Unapplied cash (10 rows):*
| Customer Payment | CP-00512 | Bell Harbor Logistics | $2,410.00 | Received 5d ago | `Unapplied` | Review |
| Customer Payment | CP-00509 | Nordline Retail Group | $980.00 | Received 6d ago | `Unapplied` | Review |
*(+8 more)*

6 + 9 + 15 + 10 = 40.

**STATUS chips** (`Pending` / `Overdue` / `Draft` / `Unapplied`): flat
outlined chips only, deliberately the opposite object language from the
clay button — 22px tall, 8px horizontal padding, **4px radius** (vs. the
button's 18px — a sharp, un-clay silhouette on purpose), 1px border, no
fill, no shadow. Label reuses meta 12/450. `Overdue` uses an invented
error text/border color `oklch(0.50 0.18 25)` (modeled on the same hue-25
error convention the sibling login comp used for its alert banner, for
consistency across the concept); the other three states use hairline
border + secondary-text, undifferentiated by color beyond that. This is a
concept-level decision worth flagging: the dispatch's restraint rule names
the "pending/in-progress status pill" as one of exactly two clay-eligible
roles system-wide — on *this* surface every status, including `Pending`,
stays a flat chip, because the surface brief says "everything else in the
worklist... stays flat/bordered/quiet, no exceptions." The clay pending
pill (if the set uses it at all) belongs on a narrower surface like
vendor-bill-detail, not on the 40-row panel where "no exceptions" is the
explicit instruction.

**ACTION column — "Review":** 14/450 accent-ink text link, right-aligned,
inline in the row — not a boxed button, no border, no fill. This is the
deliberate resolution of a real tension: the dispatch asks for a 40px
control floor on every flat control *and* a realistic 40-row load in a
900px viewport; a 40px discrete button cannot fit inside a 32px dense row
without inflating the table past what fits. Treating the row action as an
inline text link (the pattern dense grids in Gmail, Linear, and Airtable
already use below the 40px floor) keeps the row height honest to "40 rows
is the designed load" without silently violating the floor — flagged
explicitly below rather than picked quietly.

**Control floor check:** ⌘K search (320×40), all 6 rail icons (40×40 each),
and the clay button (280×56, exceeds the floor) all meet or exceed 40px.
The per-row "Review" link is the one exception, addressed above. Header is
reserved at 48px, distinct from the 40px control floor.

## Type table

| Level | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| screen title ("Finance Manager") | Inter Variable | 20px | 600 | 28px (1.4) |
| section-eyebrow ("PRESS-PANEL · ACME", column headers) | Inter Variable | 12px caps | 600 | 16px (1.33), +0.04em tracking |
| body/data (row cells, cash values, search placeholder) | Inter Variable, tabular-nums | 14px | 450 | 20px (1.43) |
| meta (labels, "AS OF", status chips, aging, sub-title) | Inter Variable | 12px | 450 | 16px (1.33) |
| clay-button label ("Approve 6 pending vendor bills") | Inter Variable | 15px | 600 | 20px (1.33) |

One face throughout, per the dispatch's reasoning that a flat panel with
one dimensional button is a material distinction, not a typographic one —
no mono face was introduced for the REFERENCE column IDs (`VB-04421` etc.),
even though the sibling login comp used IBM Plex Mono for its error
reference code; that choice belongs to a different concept's palette and
would violate this concept's "no second family" rule if carried over.

## Paired colors, at used size

*(computed via OKLCh→linear-sRGB→WCAG relative luminance by hand for this
comp; flagged "computed, not rendered" throughout, no ratio here is given
directly by the dispatch except where marked.)*

| Pair | Where used | Ratio |
|---|---|---|
| primary text `oklch(0.19 0.006 58)` on substrate `oklch(0.98 0.002 58)` | "Finance Manager" title, cash values, row body cells | 17.4:1 *(computed, not rendered)* |
| secondary text `oklch(0.44 0.008 58)` on substrate | meta labels, worklist sub-title, column headers | 7.3:1 *(computed, not rendered)* |
| accent-ink `oklch(0.40 0.10 58)` on substrate | "Review" links, active-rail tick, focus rings | 9.0:1 *(computed, not rendered)* |
| white on accent-emphasis `oklch(0.60 0.14 58)` | clay button label | **≈4.1:1** *(computed, not rendered — see "couldn't fully satisfy" below)* |
| error text `oklch(0.50 0.18 25)` (invented, modeled on login sibling's error hue) on substrate | `Overdue` status chip | 6.2:1 *(computed, not rendered)* |
| hairline border `oklch(0.86 0.005 58)` on substrate | rail divider, row rules, column-header rule, chip borders, search field border | 1.45:1 *(computed, not rendered — non-text; below the 3:1 WCAG 1.4.11 floor, see below)* |

Focus ring on every standalone control (search field, rail icons, clay
button) and every `Review` link: 2px solid accent-ink, `:focus-visible`
only, never the clay shadow stack standing in for it.

## Content direction

The screen names its operator once, at the top, in plain words — "Finance
Manager" — and immediately states the number the whole surface argues
around: 40 items waiting, 6 of which need one press before a hard 9:30
cutoff. Every value on the panel is a plausible finance-worklist figure
(cash on hand, vendor bill amounts, aging windows) at realistic magnitude
for a mid-size operation, not a round invented number standing in as data.
No brand is invented — the tenant name (`Acme`) is the same seed-data
placeholder the live app already ships, not a new fabrication for this
comp. No photo, no face: the operator is represented by initials only.

## Self-check (embarrassment gate)

Read back against the palette table above: six pairs used, four verified
comfortably passing, one (hairline) flagged as an inherited palette risk
the login sibling already surfaced, one (white-on-clay) flagged as newly
marginal on this comp's specific accent-emphasis value. Restraint rule
verified by counting: exactly one clay object exists on this canvas — the
approve button — and zero clay pills; every status chip, every rail icon,
every row link, and the search field are flat, bordered, and un-shadowed.
No second typeface was introduced despite the sibling login comp's
precedent of adding one — checked against this concept's explicit "Inter
Variable only" rule before writing the REFERENCE column. Terminology lock
held: vendor, customer, warehouse, journal entry, and item (in the rail
label and search placeholder) all appear in their canonical form; no "PO,"
"SKU," or "supplier" leaked in from habit. 40 rows is a real count, not a
rounded stand-in, and sums correctly across the four doc-type groups.
Would put a name on this.

## Couldn't fully satisfy

1. **White label on the clay button computes to ≈4.1:1**, under the 4.5:1
   the dispatch flagged as an expectation — a hand computation through the
   OKLab→linear-sRGB path (accent-emphasis `oklch(0.60 0.14 58)` resolves
   to relative luminance ≈0.205; white is 1.0; ratio ≈(1.05)/(0.255)). At
   15px/600, the label is unlikely to clear WCAG's large-text bold
   exception (which typically wants 700 weight). This is the single most
   important object on the screen having the tightest contrast margin on
   the page — worth a real contrast-tool check before Gate A, and worth
   Loop 1 considering either a slightly darker accent-emphasis (~L 0.54–0.56)
   or a 700-weight button label as the fix.
2. **Hairline border on substrate computes to ≈1.45:1**, confirming the
   same sub-3:1 finding the login sibling reported — this is a palette-wide
   condition (every hairline-bordered UI boundary in this concept, not
   just this surface) rather than something local to this comp.
3. **The 40px control floor does not reach the per-row "Review" link**,
   which lives inside a 32px dense row. Resolved here as an inline text
   link rather than a boxed control, matching how real dense grids handle
   this; flagged rather than silently decided, in case the floor is meant
   to bind literally on every clickable element regardless of row density.
