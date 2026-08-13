# chart-table: Surface 2 of 7 — Role home

Concept: chart-table. Collision: Swiss/International grid (structure) × editorial
marginalia (surface). Surface: `02-role-home` — Finance Manager's 9am dashboard.
Platform mode: N/A (desktop web, no native platform). Canvas: **1440×900**, fixed
viewport spec, full chrome, real row counts. Sticky header reserved: **48px**.

**Composition anchor: `dense-grid`** — the plotted-fix timeline and its four lanes
take the visual majority of the canvas; header and rail are subordinate chrome.
**Background mode: `flat-surface`** — one solid substrate, grid lines and markers
sit inline on it, no image or gradient. Both differ deliberately from `01-login`'s
calm center (`centered-statement` / likely `flat-surface` too, but empty) — this is
the set's first dense, working surface and should read that way against a quiet
sibling.

---

## 1. Layout move — named-grid shell, numbers

Page shell is a CSS Grid with three named column regions and two named row
regions, exact pixel widths, summing to 1440×900:

```
grid-template-rows:    [header-start] 48px  [header-end body-start] 852px [body-end]
grid-template-columns: [rail-start] 256px [rail-end content-start] 904px [content-end margin-start] 280px [margin-end]
```

- **Header** (`header-start`→`header-end`, full 1440px width, sticky `top: 0`,
  `z-index: 10`): the 48px reserved band.
- **Rail** (`rail-start`→`rail-end`, 256×852, y=48): named-grid column at rest —
  static nav, no marginalia serif inside it.
- **Content** (`content-start`→`content-end`, 904×852, y=48): the plotted-fix
  timeline. Internal padding 32px top/left/right, 24px bottom → inner box
  840×796.
- **Margin** (`margin-start`→`margin-end`, 280×852, y=48): the editorial rail.
  Empty for 852px of height except one note block, positioned to align with the
  busiest lane — "dense grid, sparse commentary" applied literally to this
  column.

### Header (1440×48, sticky)
- x=24: wordmark "Atlas", Inter 14px/600, primary text.
- x=88: running head as breadcrumb-as-title, Source Serif 4 italic 13px:
  **"Finance Manager — Today"**.
- x=1096 (right-aligned, 24px margin): persistent ⌘K search field, 320×32,
  6px radius, 1px hairline border, placeholder "Search vendors, items, journal
  entries… ⌘K" left-padded 12px, Inter 14px secondary text.

### Rail (256×852)
- Padding 20px top, 16px sides.
- Section meta label "Workspace" at y=20 (12px/450, secondary text).
- Six nav rows, 44px each, 4px gap, in locked terminology: **Dashboard**
  (active), **Items**, **Vendors**, **Customers**, **Warehouses**, **Journal
  Entries**. 16px icon + 14px label, 8px gap between.
- Active row ("Dashboard"): 2px accent-ink left bar, `accent-tint`
  (`oklch(0.95 0.02 58)`) row background, label weight 600 primary text.
  Inactive rows: label weight 450, secondary text.

### Content (840×796 inner)
Vertical stack, top to bottom:
1. **Title block**, 56px: "Finance Manager" title (20px/600) at y=0; meta
   subline "40 open items · Today, Aug 14" (12px/450, secondary text) at y=32.
2. **Gap** 24px.
3. **Axis header**, 24px: hour ticks 8–18 (11 labels, 12px/450 meta, secondary
   text), evenly spaced across the 840px track at 84px/hour.
4. **Gap** 8px.
5. **Four lanes**, 72px each, 16px gap (label row 20px + 36px marker track +
   16px internal padding), total 336px:
   - **Vendor bills due** — 18 markers (real count, matches the 40-item total)
   - **Journal entries to post** — 9 markers
   - **Customer payments expected** — 7 markers
   - **Cash position checks** — 6 markers
   - `18 + 9 + 7 + 6 = 40` — the exact number from the brief, not a rounded
     placeholder.

**Marker geometry**: 16px-diameter ring, positioned at
`left = (hour − 8) / 10 × 840px`, vertically centered in its 36px track.
Stroke encodes certainty per the palette's plotted-fix status system:
thin solid 1.5px = confirmed/posted, dashed 1.5px (3px dash) = pending/estimate,
heavy 3px = error/overdue, hollow 1.5px pale = draft, filled solid dot = closed.

**Busiest cluster** — six markers in the *Vendor bills due* lane, clustered
14:00–14:34 (`left ≈ 490–532px`, 8px stagger): three heavy red (overdue) + three
dashed blue-gray (pending same-day). This is the cluster the marginal note
explains.

Remaining content height below the lane stack (796 − 448 = 348px) is left as
scroll continuation, not force-filled — a working dashboard is allowed
whitespace below the fold; this is not a mobile safe-area band.

### Margin column (280×852)
- Padding 24px sides.
- Note block positioned at `y = 144px` from `body-start` (32px content padding
  + 56 title + 24 gap + 24 axis + 8 gap = 144px), aligning its top edge to the
  *Vendor bills due* lane — same row, adjacent column, no line drawn across the
  grid boundary between them. The alignment carries the connection; a leader
  line was considered and dropped to keep the named-grid columns structurally
  clean (see "unsatisfied" below).
- Small proofreader's tick: 24×1px hairline rule in accent-ink, y=182px
  (aligned to the cluster's vertical center in the lane track).
- Note copy, Source Serif 4 italic 13px/400, line-height 20px, max-width
  232px, color accent-ink:
  > "Six vendor bills cross their due date today — three from the same
  > vendor."
- This is the **one** marginal note on the surface — no second note anywhere
  else in the margin column, per the concept's density rule.

---

## 2. Type table

| Role | Face | Size | Weight | Line-height | Notes |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 28px | Page title ("Finance Manager") |
| Running-head / marginalia | Source Serif 4 Variable, italic | 13px | 400 | 20px | Header breadcrumb-as-title; the one margin note. Only place the serif appears. |
| Body / data | Inter Variable | 14px | 450 | 20px | tabular-nums | Nav labels, search field, note-adjacent UI text |
| Meta | Inter Variable | 12px | 450 | 16px | Axis hour ticks, section labels, item-count subline |

Both faces self-hosted, load-bearing per the direction lock. Serif is confined
to exactly two spots on this surface (header running-head, one margin note) —
everywhere else is Inter, keeping the grid's structural voice separate from
the margin's human one, per the collision sentence.

---

## 3. Palette — pairs with ratios (computed, not rendered)

All ratios below were computed by converting each `oklch()` triple to linear
sRGB (Björn Ottosson's OKLab matrices) and applying the WCAG relative-luminance
formula — **computed via script, not verified by rendering the surface**,
per this mode's constraint.

| Pair | Hex (computed) | Ratio | Reads as |
|---|---|---|---|
| primary text `oklch(0.22 0.008 58)` on substrate `oklch(0.99 0.002 58)` | `#1e1a17` on `#fdfbfa` | **16.84:1** | body/title text — far exceeds AA |
| secondary text `oklch(0.46 0.01 58)` on substrate | `#5d5753` on `#fdfbfa` | **6.94:1** | meta/nav-inactive text |
| accent-ink `oklch(0.40 0.07 58)` on substrate | `#643d1e` on `#fdfbfa` | **9.14:1** | margin note, focus ring — brief expected ≥7:1, **exceeds** |
| white on accent-emphasis `oklch(0.58 0.10 58)` | `#ffffff` on `#a66a3a` | **4.41:1** | brief expected ≥4.5:1 white-on-it — **computed slightly under** (see §5) |
| accent-dark `oklch(0.70 0.08 58)` on dark substrate `oklch(0.16 0.004 58)` | `#c4926c` on `#0f0d0c` | **7.12:1** | dark-mode accent text |
| dark-mode text `oklch(0.93 0.005 58)` on dark substrate | `#eae7e5` on `#0f0d0c` | **15.78:1** | dark-mode body |
| status "error/overdue" (heavy ring, H≈25°) on substrate | `#b94642` on `#fdfbfa` | **5.08:1** | ring is non-text; clears text AA too |
| status "confirmed/posted" (thin ring, H≈145°) on substrate | `#4d9351` on `#fdfbfa` | **3.65:1** | non-text UI component (WCAG 1.4.11, 3:1 floor) — **clears, narrowly** |
| status "pending" (dashed ring, H≈240°) on substrate | `#57768c` on `#fdfbfa` | **4.67:1** | non-text component — clears comfortably |
| status "draft" (hollow gray ring) on substrate | `#b0adab` on `#fdfbfa` | **2.16:1** | non-text component — **fails the 3:1 floor** (see §5) |
| status "closed" (filled dark ring) on substrate | `#322d29` on `#fdfbfa` | **13.27:1** | clears everything |
| hairline border on substrate | `#e1ddda` on `#fdfbfa` | **1.31:1** | decorative structural divider only, not a text/component pair — not held to a contrast floor |

---

## 4. Content direction

One line: real day-shaped numbers, not a populated demo — 40 open items split
18/9/7/6 across four honest lanes, one prose sentence that explains the single
loudest pattern instead of forty tooltips, and the product's real name
("Atlas") standing in for a wordmark instead of an invented brand.

---

## 5. Embarrassment gate — self-check

Read the numbers above back against the palette table before returning:

- **Palette hexes**: all seven source `oklch()` values converted and matched
  to the table above; nothing substituted.
- **Body-size legibility**: 14px body and 12px meta both clear 6.9:1+ against
  substrate — plausible at normal viewing distance.
- **Two findings, flagged rather than papered over** (see §6) — the
  white-on-accent-emphasis pair computes to 4.41:1, just under the brief's
  ≥4.5:1 expectation, and the draft-status ring at 2.16:1 misses the 3:1
  non-text floor entirely.
- **Four-band rule**: not applicable — this is a desktop tool-shaped surface,
  not mobile; the 48px sticky header is the equivalent reserved band and is
  held exactly, per the dispatch.
- **Collision readable**: yes — the named-grid shell (three fixed columns, a
  ticked axis, four ruled lanes) carries the machine-order half; the one
  italic serif note in an otherwise-empty margin column carries the
  human-verified half. Neither bleeds into the other's territory.
- **Composition differs from neighbors**: `dense-grid` / `flat-surface`
  against login's presumed `centered-statement` calm — logged honestly, not
  nudged for variety.
- **No garbled text, no invented logo, no fake superlative**: note copy is a
  plausible single real sentence at real length; "Atlas" is the actual product
  name, not invented; no numbers presented as real data beyond the stated
  synthetic 40/18/9/7/6 breakdown, which is structural, not a claim.

Would a designer put their name on this? Yes, with the two contrast
adjustments named in §6 taken into production, not deferred silently.

---

## 6. Anything unsatisfied

- **`white` on `accent-emphasis` computes to 4.41:1**, not the ≥4.5:1 the
  brief expected. Reads fine for text ≥14px/700 or ≥18px/400 (large-text AA
  floor is 3:1), so it's safe on a button label at the sizes this surface
  actually uses it — but it should not be used for small (<14px) white text on
  that fill without darkening the emphasis token slightly (e.g., toward
  `L≈0.55`).
- **The "draft" hollow-gray ring fails the 3:1 non-text floor at 2.16:1.**
  This surface's real-count lanes don't currently need a draft marker, so it
  doesn't appear in the 40, but the token as specified would fail on a surface
  that does use it. Needs either a darker gray (`L≈0.65` gets it close to 3:1)
  or a heavier stroke/fill to compensate — flagging rather than shipping it
  quietly.
- **No leader line from the margin note to the cluster it explains** — the
  note and the cluster share a row but sit in separate grid columns with the
  content column between them. I aligned them vertically instead of drawing a
  connector across the content column, to keep the named-grid boundaries
  structurally intact; a future pass could add a thin SVG leader if user
  testing shows the alignment alone doesn't read as connected.
