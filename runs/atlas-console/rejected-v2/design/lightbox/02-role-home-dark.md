# lightbox: Surface 2 of 7 — Role Home (dark)

**Mode:** dark · **Canvas:** 1440×900 (fixed coded viewport, web/desktop-only, full chrome) ·
**Composition anchor:** `left-rail-caption` · **Background mode:** `flat-surface`

Same screen, same numbers, dark palette. Every pixel value, gap, row height, and the keyboard/
interaction model are unchanged from the light comp — only fills, text tokens, and the glass
bar's "two art directions" rule differ (`DIRECTION.md` §7: light mode runs more opaque and less
blurred, dark mode runs less opaque and reads through more — declared explicitly, not inverted
naively).

---

## Layout — numbers

Base unit: 8px. Control floor: 44px. All positions below are identical to the light spec; only
the token values change.

### The one glass object — canonical definition for this concept (dark)

- **Position:** unchanged — `fixed; top:0; left:0; width:1440px; height:64px; z-index:50`,
  edge-to-edge, above the rail and the content column.
- **Fill:** `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` +
  `backdrop-filter: blur(20px)` — dark drops the `saturate(140%)` light carries; less opaque,
  reads through more, per the concept's own stated dark-mode divergence. Border, bottom edge,
  1px: `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)`.
- **Contents:** unchanged layout from light — search trigger (320×44px, same "⌘K  Search or
  jump to a record" copy, same combobox-on-activate behavior), quick-create `+` (44×44px,
  `aria-label="New item"`), 12px gap, notifications bell (44×44px, `aria-label="Notifications"`,
  same 8px presence-dot convention). All three sit on the dark scrim fill (below), not bare on
  the blur, same reasoning as light: icons need guaranteed contrast against a moving background
  exactly like text does.
- **Text/icon scrim:** `color-mix(in oklab, oklch(0.22 0.015 290) 80%, transparent)` — derived
  here, not restated verbatim from `DIRECTION.md` §7, which gives the *rule* ("same scrim rule,
  re-measured on dark") without a separate numeric value for dark. Constructed the same way the
  light value was: the panel's own base hue (`oklch(0.22 0.015 290)`) at a materially higher
  opacity than the panel itself (80% vs. the panel's 50%), so text and icons sit on a
  near-solid dark chip rather than raw blur. **Flagged as derived, not given** — confirm this
  exact number at Loop 2 alongside the light value's own re-measurement.
- **Reduced motion:** same as light — instant opaque-bordered panel, never animates into a blur.
- **Below `y=64px`, nothing is glass.** Same line as light.

*Same cross-surface note as the light file: Surface 3 (dark) states "36×36px, same as light" for
these two icon-buttons at this same 64px bar; this file's canonical 44×44px is the run's own
stated primary-control floor. Flagged for Loop 2 reconciliation, not silently matched.*

### Left rail — flat, opaque, icon + label (dark)

- Same footprint as light: `fixed; top:64px; left:0; width:240px; height:836px`. `substrate`
  fill, `1px solid hairline` right border. No blur.
- Same nav list, same order: **Home** (active — this screen), Finance, Inventory, Procurement,
  Manufacturing, Sales, CRM, Projects, Quality, Maintenance, HR, Admin, Reporting, then **Help**
  pinned last.
- **Active state ("Home"):** `accent-tint-dark` fill, `accent-dark` text and icon, `3px`
  `accent-dark` bar on the row's left edge — same double-signal rule as light.

### Main content column — same positions as light

`x:240–1440` (1200px), inner padding 32px → content 1136px wide, content starts `y:96`.

1. **`<h1>` "Home"** — 20px/600, `text-primary`. `y:96–124`. No breadcrumb, same reasoning as
   light.
2. 8px gap → subtitle, 14px/450, `text-secondary`: "Your queue — purchase orders, vendor bills,
   and receipts awaiting action." `y:132–152`.
3. Same three sections at the same y-offsets as light: Due today `y:184`, Due this week `y:468`,
   Everything else `y:808`.

Same section anatomy, same row anatomy (56px rows, status dot + two-line text block + right-hand
value, hairline divider, `row-alt` on hover/focus-within), same content — the three tables below
repeat the light spec's data so this file is a complete standalone reference, not a diff a
builder has to cross-reference.

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

**Section 3 — "Everything else" (1 of 23 shown, "View all →")** — `y:808–892`, cropped by the
canvas edge at `y:900`, same as light:

| Dot | Record · counterparty | Context | Value |
|---|---|---|---|
| ● posted | PO-2026-00801 · Norbright Industrial | Fully received and closed | $8,410.00 |

### Worst-case scrolled frame (dark) — same scroll math as light

At `scrollTop: 264px`, the same overdue row (`BILL-2026-01187`, hue 25°, solid triangle,
`y:268–324` in the resting layout) maps to screen `y:4–60`, entirely within the fixed bar's
`0–64` band, blurred beneath the dark glass. Dark mode's lighter 50%-opacity panel reads through
*more* than light's 60%, so this is arguably the harder of the two frames to hold contrast
against — flagged with the same urgency as light for a Loop 2 script pass, not assumed to
inherit light's result.

### Interaction model, skip link, landmarks, focus ring

Unchanged from light in structure. Focus ring: `2px solid accent-dark`, `2px` offset,
`:focus-visible` only, checked against `substrate`, `row-alt`, and the dark glass bar's scrim
fill at the worst-case frame above — the same three-background check as light, run again here
rather than assumed to transfer.

---

## Type

Identical scale and roles to light — only color changes (see table below). No JetBrains Mono,
no second face.

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| Title (h1) | Inter Variable | 20px | 600 | 28px |
| Section header (h2, styled small) | Inter Variable | 12px | 450 | 16px |
| Body / data | Inter Variable | 14px | 450 | 20px — `tabular-nums` |
| Meta | Inter Variable | 12px | 450 | 16px |
| Command-bar label | Inter Variable | 14px | 500 | 20px |

---

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / row default | substrate | `oklch(0.155 0.01 290)` | text-primary `oklch(0.95 0.006 290)` | ~15:1 |
| Row hover/focus-within fill, rail row highlight (non-active) | row-alt | `oklch(0.205 0.012 290)` | text-primary | ~13:1 |
| Subtitle, section headers, row context line, "View all," rail inactive labels | text-secondary | `oklch(0.70 0.014 290)` | on substrate | ~6:1 |
| Row divider, rail edge, search-trigger/icon-button border | hairline | `oklch(0.33 0.014 290)` | — decorative only |
| Active-nav text/icon/bar, "View all" link, focus ring | accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 |
| Active-nav row fill | accent-tint-dark | `oklch(0.28 0.045 290)` | accent-dark | ~5:1 |
| Notification presence dot only | accent-dark | `oklch(0.77 0.13 290)` | — 8px decorative dot, not text; dark mode reuses `accent-dark` here rather than a separate emphasis token, since this run's dark palette doesn't define its own accent-emphasis-dark |
| **Glass command bar (dark)** | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `backdrop-filter: blur(20px)`, border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)` | text/icon scrim `color-mix(in oklab, oklch(0.22 0.015 290) 80%, transparent)` — derived, flagged above | re-measure at build, harder case than light per the note above |
| Status: posted/success (● solid circle) | — | `oklch(0.68 0.14 150)` | non-text, 3:1 graphical floor | estimated ~4:1 on substrate |
| Status: pending (◐ striped circle) | — | `oklch(0.70 0.13 80)` | non-text | estimated ~3.5:1 on substrate, verify at build |
| Status: error/overdue (▲ solid triangle) | — | `oklch(0.65 0.17 25)` | non-text | estimated ~3.8:1 on substrate |
| Status: draft (○ outlined circle, stroke only) | — | stroke = text-secondary `oklch(0.70 0.014 290)` | non-text | inherits text-secondary's ~6:1 |

Same discipline as light: no text run or button fill on this screen uses a borderline pairing —
the only near-edge value anywhere is the derived dark scrim, and that's flagged explicitly
above, not folded quietly into the ratio column as if it were settled.

---

## Content direction

Identical to light — same terminology lock (item / vendor / warehouse), same record numbers and
counterparty names, same section counts, no invented brand or persona. Dark mode changes no
copy, only tokens.

---

## Self-check (embarrassment gate)

Same read-back as light, against this file's own dark color table: every pairing traces to a
stated or explicitly-derived-and-flagged ratio, none silently assumed. The dark glass panel
correctly runs less opaque than light (50% vs. 60% mix) with `saturate` dropped, matching the
concept's stated divergence rather than a naive value inversion. Status hues use the dark
variants given for this screen, not light's numbers re-used by mistake. Would put my name on
this.
