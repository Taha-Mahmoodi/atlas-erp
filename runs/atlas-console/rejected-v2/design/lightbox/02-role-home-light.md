# lightbox: Surface 2 of 7 — Role Home (light)

**Mode:** light · **Canvas:** 1440×900 (fixed coded viewport, web/desktop-only, full chrome) ·
**Composition anchor:** `left-rail-caption` · **Background mode:** `flat-surface`

**Job:** the first screen a signed-in buyer sees. It has to make one thing legible in under a
second — what actually needs this person's attention today — without a single card, shadow, or
color-blocked lane doing that work for it. Hierarchy is carried by type size, weight, and
whitespace alone, and by exactly one shape+hue status grammar. This is also **the anchor
screen**: the floating glass command bar is defined here first: surfaces 3–6 all read "same
spec as Surface 2, kept brief" and inherit these numbers rather than restating them.

---

## Layout — numbers

Base unit: 8px. Control floor: 44px (primary controls only — dense row-level clusters would use
the WCAG 2.5.8 spacing exception; this screen has none, since even the status dot is a
non-interactive label, not a widget — see "Interaction model," below).

### The one glass object — canonical definition for this concept

- **Position:** `fixed; top:0; left:0; width:1440px; height:64px (8u); z-index:50`. Spans the
  full canvas width, above both the rail and the content column — nothing on this screen (or
  any screen in this concept) renders above it. Edge-to-edge, not a floating inset pill: a
  "reserved sticky-chrome" bar reads most literally as a strip you scroll *under*, not a panel
  you scroll *near*, so it isn't rounded and doesn't sit inset from the canvas edges.
- **Fill:** `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` +
  `backdrop-filter: blur(20px) saturate(140%)`. Border, bottom edge only, 1px:
  `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)` — the light-catching edge that
  reads as glass rather than frosted plastic.
- **Contents**, left to right, 24px outer padding, vertically centered in the 64px strip:
  1. **Search trigger** — `320×44px`, `12px` radius, `1px solid hairline`, filled with the
     text-scrim color itself (see below) rather than sitting bare on the blur. Leading 16px
     search icon (`text-secondary`), label "⌘K  Search or jump to a record" in
     command-bar-label scale (14px/500), `text-secondary`. Activating it (click, Enter, or the
     `⌘K`/`Ctrl+K` global shortcut per `TOOLS.md` §3/§7) turns it into a real combobox: text
     input + `listbox` popup of matches across items, vendors, bills, and record numbers — the
     same `listbox` combobox pattern already budgeted for reference-pickers elsewhere in this
     run (`ACCESS.md` decision row 19), not a sixth ARIA pattern.
  2. Flexible spacer (there is a lot of open bar left over at this width — the bar is not
     stretched to fill it; empty glass is the calmer, more restrained choice than padding it out
     with decoration).
  3. **Quick-create** — `44×44px` icon-button, `+` glyph, `aria-label="New item"`. Navigates
     directly to Surface 5 (New item form). Single action, not a menu — this concept budgets
     exactly one real `menu` pattern for the whole run (a row's "⋯ more actions" overflow,
     `ACCESS.md` row 17), and this isn't it.
  4. 12px gap → **Notifications** — `44×44px` icon-button, bell glyph,
     `aria-label="Notifications"` (count spoken in the name when non-zero, e.g. "Notifications,
     3 unread" — no visible numeral badge; a small 8px `accent-emphasis` presence dot at the
     glyph's top-right corner is the only visual cue, decorative, never the sole signal since
     the accessible name carries the actual count). 24px right padding after this control.
  - Both icon-buttons sit on the same scrim fill as the search trigger (a filled 44×44 chip,
    `12px` radius, `1px solid hairline`) rather than bare on the glass — a glyph needs
    guaranteed contrast against whatever's blurring behind it exactly as much as a text run
    does, so the scrim rule is extended to icon-only controls here, not just labelled ones.
  - No brand mark and no account/avatar control on this bar — the rail carries navigation
    identity, and an account affordance isn't one of this run's seven numbered surfaces, so it's
    left out rather than half-specified.
- **Text scrim** (every text run *and* every icon on the bar sits on one): `background:
  color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)` — per `DIRECTION.md` §7's stated
  glassmorphism fix. **Flagged, not assumed passing:** this is measured against a calm
  background; it needs re-measurement at build against the actual busiest frame that can scroll
  beneath it. See "Worst-case scrolled frame," below, for what that frame is on this screen.
- **Reduced motion:** the blur-in on first paint degrades to an instant opaque-bordered panel —
  never animates into or out of a blur (`ACCESS.md` decision row 11).
- **Below `y=64px`, nothing is glass.** Rail and content are `substrate`/`accent-tint` fills
  with zero `backdrop-filter`. That line is the whole collision, drawn once, in pixels.

*Cross-surface note: Surface 3 (Items List) already references this bar as "36×36px" icon
buttons at the same 64px height; Surface 5 (New item form) independently specifies a 56px bar
with 44×44px controls; Surface 6 (Empty state) specifies a floating 56px inset pill with
rounded corners. This file is the canonical definition per its own "anchor screen" brief —
44×44px (the run's own stated primary-control floor, `ACCESS.md` row 1) and a 64px edge-to-edge
strip, not a floating pill. The deltas above are flagged for Loop 2 reconciliation, not silently
matched or silently overridden in the other files.*

### Left rail — flat, opaque, icon + label, discoverability path (not the fast path)

- `position: fixed; top:64px; left:0; width:240px; height:836px`. `substrate` fill, `1px solid
  hairline` right border. No blur, no shadow.
- 16px padding. Nav rows, 44px height each, 20px icon + 8px gap + 14px/450 label: **Home**
  (active — this screen), Finance, Inventory, Procurement, Manufacturing, Sales, CRM, Projects,
  Quality, Maintenance, HR, Admin, Reporting.
- **Active state ("Home"):** `accent-tint` fill on that one row, `accent-ink` text and icon,
  `3px` `accent-ink` bar on the row's left edge — a second signal beyond the fill color, per the
  "never color alone" rule this concept already applies to status dots (`ACCESS.md` row 10),
  extended here to nav current-state for the same reason. `aria-current="page"` on the anchor.
- Flex spacer, then **Help** pinned last — same relative position on every screen, both concepts
  (`ACCESS.md` decision row 8).
- `<nav aria-label="Primary">` landmark wraps this whole rail.

### Main content column — `x:240–1440` (1200px), inner padding 32px → content 1136px wide

Content starts at `y = 64 + 32 = 96`. `<main>` landmark wraps everything below, `<h1
tabindex="-1">` is the route-change focus target (`ACCESS.md` decision row 13).

1. **`<h1>` "Home"** — 20px/600, `text-primary`. `y:96–124`. The one h1 on the screen. No
   breadcrumb above it — Home is the rail's own root entry, nothing sits above it in the
   hierarchy, so a breadcrumb would name a parent that doesn't exist.
2. 8px gap → **subtitle**, one line, body scale (14px/450), `text-secondary`: "Your queue —
   purchase orders, vendor bills, and receipts awaiting action." `y:132–152`.
3. 32px gap → **Section 1: "Due today"** starts at `y:184`.
4. 32px gap → **Section 2: "Due this week"** starts at `y:468`.
5. 32px gap → **Section 3: "Everything else"** starts at `y:808`.

Each section is a real `<section aria-labelledby="…">` with a real `<h2>` — styled small (see
Type, below) so it never competes with the h1 visually, but a genuine heading level for
assistive tech, not a styled `<div>` standing in for one.

**Section anatomy** (identical structure, three instances):

- **Header row**, 12px/450 meta scale, `y+0` to `y+16`: `<h2>` label rendered
  `text-transform: uppercase; letter-spacing: 0.04em`, `text-secondary` — e.g. "DUE TODAY · 4".
  When the section holds more records than are shown, a right-aligned "View all →" link sits on
  the same line, 12px/450, `accent-ink`.
- 12px gap → **rows start**, `y+28`.
- **Row** — `56px` height (comfortably clears the 44px control floor; the whole row is one
  `<a>`, the interactive target), full 1136px width, `1px solid hairline` bottom border
  (ordinary hairline rows, same device the grid screens use — `substrate` fill at rest,
  `row-alt` fill on `:hover`/`:focus-within`, no radius on the hover fill so it reads as a
  highlighted table row, never a card):
  - **Status dot** — 16×16px shape, left edge `x+16` from the row's left, vertically centered
    across both text lines. See "Status vocabulary," below.
  - 16px gap → **two-line text block**, left-aligned, `max-width: 640px`, ellipsis-truncates:
    - Line 1: record identifier + counterparty, body/data scale (14px/450 tabular-nums for the
      identifier), `text-primary`. E.g. "PO-2026-00842 · Meridian Supply Co."
    - Line 2: one-line context, meta scale (12px/450), `text-secondary`. E.g. "Awaiting your
      approval."
  - Flexible spacer.
  - **Right-hand value** — right-aligned, body/data scale (14px/450, `tabular-nums`),
    `text-primary`: an amount, a date, or a time, whichever is the record's actual due-relevant
    figure. `24px` right padding to the row's edge.
  - Accessible name on the row `<a>` combines all four facts in one string, never relying on the
    dot's color alone: `aria-label="Pending — Purchase order PO-2026-00842, awaiting your
    approval, due today, $4,280.00, vendor Meridian Supply Co."`

**Section 1 — "Due today" (4 of 4, all shown)** — `y:184–436`:

| Dot | Record · counterparty | Context | Value |
|---|---|---|---|
| ◐ pending | PO-2026-00842 · Meridian Supply Co. | Awaiting your approval | $4,280.00 |
| ▲ error | BILL-2026-01187 · Cascade Fasteners | 3-way match discrepancy — receipt and invoice disagree | $1,096.50 |
| ○ draft | PO-2026-00845 · Norbright Industrial | Draft — item lines incomplete | $780.00 |
| ◐ pending | RFQ-2026-00212 · 3 vendors invited | Vendor responses due today | 5:00 PM |

**Section 2 — "Due this week" (5 of 9 shown, "View all →")** — `y:468–776`:

| Dot | Record · counterparty | Context | Value |
|---|---|---|---|
| ● posted | BILL-2026-01190 · Solara Components | Posted — payment due Friday | $12,450.00 |
| ◐ pending | PO-2026-00839 · Ashgrove Metals | Awaiting vendor confirmation | $3,120.00 |
| ○ draft | PO-2026-00847 · Meridian Supply Co. | Draft — item lines incomplete | $960.00 |
| ◐ pending | BILL-2026-01193 · Cascade Fasteners | Awaiting your approval | $2,275.00 |
| ● posted | GR-2026-00560 · Warehouse — Plant 3, Denver | Goods receipt posted, matched to PO-2026-00801 | Aug 18 |

**Section 3 — "Everything else" (1 of 23 shown, "View all →")** — `y:808–892`, then the canvas
edge at `y:900` crops the rest, same as it would crop a real scrolled page — the remaining 22
rows use the identical row template, real record numbers and vendors, not a repeated placeholder
row:

| Dot | Record · counterparty | Context | Value |
|---|---|---|---|
| ● posted | PO-2026-00801 · Norbright Industrial | Fully received and closed | $8,410.00 |

**Row count and scroll:** every row above uses the exact same markup — one `<a>`, one dot, two
text lines, one value, one hairline. Nothing about row 23 differs structurally from row 1; the
opaque data layer is flat by construction, so the row count is free, same as the density proof
on the items-list screen.

### Worst-case scrolled frame (for the scrim re-measurement — not the resting state above)

The layout above is the resting state (`scrollTop: 0`), and it already fits inside the 900px
canvas without scrolling. But the glass bar's scrim needs to be checked against what it looks
like once the page *has* scrolled, since that's the actual failure mode the scrim exists for. At
`scrollTop: 264px` (33 base-units), row 2 in "Due today" — the overdue/error-triangle row,
`y:268–324` in the resting layout above, the highest-chroma, busiest content on this screen —
maps to screen `y:4–60`, entirely inside the fixed bar's `0–64` band: fully blurred beneath it,
not just grazing its edge. That is the frame this concept's own note means by "busiest table row
scrolling beneath it": a solid-triangle error shape at hue 25° plus body-weight text, blurred to
20px, sitting directly behind the search trigger's left edge. The scrim must hold contrast at
that frame, not just at rest — flagged for a real script pass at Loop 2, not assumed passing
here.

### Interaction model — not a `role="grid"`

This worklist is a plain set of navigable links, not the entered-cell grid pattern used on
Surfaces 3/4. Each row is one `<a>` inside an `<li>`; Tab moves between rows in document order;
Enter/click opens the record's own detail screen (a full opaque screen, never a floating panel —
the concept's own rule that a record's detail is content, not a glass surface). The status dot
is a labelled, non-interactive glyph inside that link's accessible name, not a separate
inline-editable widget — inline status editing is reserved for the grid screens, so this screen
doesn't spend a second ARIA pattern it doesn't need.

### Skip link, landmarks, focus ring

- **Skip link** — first in DOM/tab order, visually hidden until `:focus-visible`, then fixed
  `top:16px; left:16px`, `accent-ink` background, white text, 14px/600, `8px 16px` padding, 8px
  radius, above everything including the glass bar. Copy: "Skip to your queue" — targets the h1.
- **Landmarks:** one `<main>`, one `<nav aria-label="Primary">` (the rail), one `<header
  role="banner">` (the glass bar).
- **Focus ring:** `2px solid accent-ink`, `2px` offset, `:focus-visible` only. Checked against
  three distinct backgrounds this screen actually puts a focus target on: the opaque `substrate`
  (rows, h1 area) — the concept's own stated ~7.2:1 pairing, comfortable; `row-alt` (hovered
  rows) — same ring color, same margin, no meaningful delta; and the glass bar's own scrim fill
  at its worst-case scrolled frame above — this is the one surface in the run where the ring's
  own backdrop moves, so it's checked there explicitly rather than assumed to inherit the
  substrate's number (`ACCESS.md` decision row 4).

---

## Type

| Role | Face | Size | Weight | Line-height | Color |
|---|---|---|---|---|---|
| Title (h1) | Inter Variable | 20px | 600 | 28px | `text-primary` |
| Section header (h2, styled small — semantic level, not visual size) | Inter Variable | 12px | 450 | 16px | `text-secondary`, uppercase, 0.04em tracking |
| Body / data (row identifier, right-hand value, subtitle) | Inter Variable | 14px | 450 | 20px — numeric runs `tabular-nums` |
| Meta (row context line, "View all" link) | Inter Variable | 12px | 450 | 16px |
| Command-bar label | Inter Variable | 14px | 500 | 20px |

No JetBrains Mono, no second face anywhere — record identifiers (`PO-2026-00842`,
`BILL-2026-01187`) get tabular figures from Inter's own numeric OpenType feature, exactly like
the grid screens, so an identifier never looks like it belongs to a different material than the
rest of the row.

---

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / row default | substrate | `oklch(0.99 0.003 290)` | text-primary `oklch(0.20 0.012 290)` | ~16:1 |
| Row hover/focus-within fill, rail row highlight (non-active) | row-alt | `oklch(0.965 0.006 290)` | text-primary | ~15:1 |
| Subtitle, section headers, row context line, "View all," rail inactive labels | text-secondary | `oklch(0.47 0.015 290)` | on substrate | ~6.3:1 |
| Row divider, rail edge, search-trigger/icon-button border | hairline | `oklch(0.90 0.008 290)` | — decorative only, sub-3:1; the actual boundary signal is the fill change or the layout gap, never this line alone |
| Active-nav text/icon/bar, "View all" link, focus ring | accent-ink | `oklch(0.43 0.15 290)` | white / on substrate | ~7.2:1 |
| Active-nav row fill | accent-tint | `oklch(0.95 0.03 290)` | accent-ink | ~6:1 |
| Notification presence dot only | accent-emphasis | `oklch(0.52 0.18 290)` | — 8px decorative dot, not text; the run's ~4.9:1 borderline pairing is never used for a text run on this screen |
| **Glass command bar** | `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` + `backdrop-filter: blur(20px) saturate(140%)`, border `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)` | text/icon scrim `color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)` | measured against a calm frame; re-measure against the worst-case scrolled frame above before trusting it |
| Status: posted/success (● solid circle) | — | `oklch(0.58 0.15 150)` | non-text, 3:1 graphical floor | estimated ~4.5:1 on substrate, not script-verified |
| Status: pending (◐ striped circle) | — | `oklch(0.62 0.14 80)` | non-text | estimated ~3.2:1 on substrate — amber reads lower-contrast at equal L than the other three hues; verify first at build |
| Status: error/overdue (▲ solid triangle) | — | `oklch(0.55 0.19 25)` | non-text | estimated ~4:1 on substrate |
| Status: draft (○ outlined circle, stroke only) | — | stroke = text-secondary `oklch(0.47 0.015 290)` | non-text | inherits text-secondary's ~6.3:1, comfortably clears the 3:1 floor |

`accent-emphasis` at its full ~4.9:1-borderline white-foreground pairing (the run's own flagged
RISK 4) is **not used for any text or button fill on this screen** — the only place it appears
is an 8px non-text presence dot, which only needs the 3:1 graphical floor it already clears
against `substrate`.

---

## Content direction

Real procurement nouns throughout, terminology-locked: "item," never "product" or "SKU";
"vendor," never "supplier"; "warehouse" for the goods-receipt row. Record numbers
(`PO-2026-00842`, `BILL-2026-01187`, `RFQ-2026-00212`, `GR-2026-00560`) and counterparty names
are plausible-length sample data, structurally consistent within this one spec, not a marketing
claim or fabricated statistic. Section counts ("4," "9," "23") match the shown/total split
stated next to each — no invented second number sitting uncorroborated beside them. No brand
name beyond "Atlas" itself, no logo, no invented persona on the notifications or account
affordances (there is no avatar on this bar at all — see "Contents," above).

---

## Self-check (embarrassment gate)

Read back against the color table: every text pairing traces to a stated ratio or an explicit
"estimated, not verified" flag, matching this run's own §11 disclosure convention. No card, no
shadow, no bento lane anywhere below `y=64px` — confirmed against the concept's central rule.
Exactly one glass object, defined once, with its border/fill/scrim numbers matching
`DIRECTION.md` §7 verbatim. Status grammar is shape-first (circle/triangle, filled/outline/
striped) with hue as the second signal, never color alone, and every dot's accessible name
states state + record + due-ness, never a bare glyph. One h1, real h2 section landmarks, skip
link, focus ring checked against the one surface where its backdrop actually moves. Would put my
name on this.
