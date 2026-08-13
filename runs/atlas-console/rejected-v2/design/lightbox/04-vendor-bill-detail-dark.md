# lightbox: Surface 4 of 7 — Vendor Bill Detail
**Mode:** dark · **Canvas:** 1440×900 fixed viewport, coded spec, full chrome · **Platform:** web/desktop-only

**Composition anchor:** `right-rail-caption` — unchanged from light: wide left field (line-items
grid) as the record's real content, narrow right rail (document-flow chain) as inspector/detail
metadata.

**Background mode:** `flat-surface` — one solid opaque substrate (`oklch(0.155 0.01 290)`) under
everything except the one glass object. Same argument as light: nothing behind the data layer but
itself, in either art direction.

Layout, region map, and every pixel/spacing number are unchanged from the light spec (§1's table,
§7's 32/900/32/444 split, §8's list structure) — dark mode is a second art direction on the same
one design, per the concept's own rule ("the opaque data layer is one design in two palettes").
Only color and the glass mix ratio differ, stated below.

---

## 1. Glass command bar (dark art direction — a different mix, not an inversion)

- Fixed, full-width, height 64px, same position as light.
- Fill: `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` (50% mix vs. light's 60% —
  dark mode reads through more, per `STYLES.md`'s stated rule, declared explicitly rather than
  inverted naively), `backdrop-filter: blur(20px)` (no `saturate(140%)` boost needed on dark).
  Border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)`.
- Text scrim, re-measured for dark: same construction as light, `color-mix(in oklab, oklch(0.22
  0.015 290) 78%, transparent)`, flagged for build-time re-measurement against the busiest row
  scrolling beneath it (RISK 1, dark side).
- Same contents as light: search field only, no quick-create on a detail screen.

## 2. Back link

- `← Back to Vendor Bills`, plain flat text link, first in content flow, same 44px hit zone.
- Color `accent-dark oklch(0.77 0.13 290)` on `substrate oklch(0.155 0.01 290)` (~6.5:1). Underline
  on `:hover`/`:focus-visible` only.

## 3. Title + bill status

- `<h1 id="main-content" tabindex="-1">Vendor Bill BILL-2026-00003</h1>` — 20px/600, `text-primary
  oklch(0.95 0.006 290)`.
- Same pending status dot (half-filled/striped, H80) + "Pending approval" label, same size/weight
  as light. Shape carries the state; hue is a second channel, never the only one.

## 4. Metadata row

| Field | Label (12px/450, `text-secondary oklch(0.70 0.014 290)`) | Value (14px/450 tabular, `text-primary`) |
|---|---|---|
| Vendor | "Vendor" | Meridian Office Supplies |
| Amount | "Amount" | $1,874.34 |
| Due date | "Due date" | 2026-04-11 |

Same figures as light — this is one record, not a re-derived one.

## 5. Actions row

- **Approve** — plain flat, `accent-dark oklch(0.77 0.13 290)` fill. Note the swap: light uses
  `accent-emphasis` (white-on-accent, ~4.9:1, borderline); dark has no separate emphasis token, so
  Approve fills with `accent-dark` and sets **dark text** on it (`substrate` color, `oklch(0.155
  0.01 290)`), which measures far cleaner than white-on-accent would on this lighter dark-mode
  accent — stated explicitly rather than assumed, since the light palette's own emphasis pairing is
  flagged borderline (RISK 4) and dark shouldn't inherit that risk silently.
- **Void** — plain flat, hairline border `oklch(0.33 0.014 290)`, `text-primary` interior. Opens
  the void modal (§8).

## 6. Left field — line-items grid (`role="grid"`)

Same header row, same 5 line items, same totals as light — figures don't change with theme:

| Item | Qty | Unit price | Line total |
|---|---:|---:|---:|
| A4 Copy Paper, 80gsm | 200 | $4.20 | $840.00 |
| Toner Cartridge — Black | 12 | $38.50 | $462.00 |
| Desk Organizer Tray | 30 | $9.75 | $292.50 |
| Whiteboard Markers (Pack of 12) | 15 | $6.40 | $96.00 |
| Shipping & Handling | 1 | $45.00 | $45.00 |

Subtotal $1,735.50 · Tax (8%) $138.84 · **Total $1,874.34**.

- Header labels: meta 12px/450, `text-secondary`, bottom hairline `oklch(0.33 0.014 290)`.
- Zebra banding on even rows: `row-alt oklch(0.205 0.012 290)`. Hairline divider `oklch(0.33 0.014
  290)` between every row. Tabular-nums, right-aligned, decimal-aligned throughout.

## 7. Right rail — document-flow chain

Same three stages, same dates, same checked-by names, same shape vocabulary and accessible-name
strings as light — the chain is data, not a themed asset:

| Stage | Record | Date | Checked by | Dot | Accessible name |
|---|---|---|---|---|---|
| Purchase Order | PO-2026-00081 | issued 2026-03-02 | J. Alvarez | solid circle, H150 | "Approved — PO, checked 02 Mar" |
| Goods Receipt | GRN-2026-00114 | received 2026-03-09 | T. Osei | solid circle, H150 | "Approved — GRN, checked 09 Mar" |
| Vendor Bill | BILL-2026-00003 (this record) | entered 2026-03-12 | — awaiting review | half-filled/striped circle, H80 | "Pending approval — Bill, awaiting review" |

Dot fill hues stay the same H150/H80/H25 vocabulary at a lightness tuned for the dark substrate
(not specified further here since no new palette value was given for dot fills — build should
verify H150/H80/H25 at a lightness that clears 3:1 against `oklch(0.155 0.01 290)`, same caveat
STYLES.md already carries for token/dot fills elsewhere in this run).

## 8. Void confirmation modal

- Overlay: flat solid scrim, `oklch(0.02 0 0 / 0.55)` (darker, more opaque than light's 0.4 — a
  light scrim on a dark substrate reads as a wash, not a dim), **no blur**, same rule as light: a
  decision worth confirming never gets glassed.
- Panel: opaque `substrate oklch(0.155 0.01 290)`, 1px hairline border `oklch(0.33 0.014 290)`, no
  shadow, 400px wide, centered, 24px padding.
- Heading: "Void this bill?" (h2, title role, 20px/600, `text-primary`).
- Body: "This can't be undone. BILL-2026-00003 will be marked void and removed from the payable
  balance." (14px/450, `text-secondary`).
- Buttons: **Cancel** (plain flat, hairline border, initial focus on open) and **Void** (plain
  flat, hairline border, `text-primary` — no filled accent; fill stays reserved for Approve).
- Focus contract identical to light (`ACCESS.md` row 16): initial focus on Cancel, trap in dialog,
  `Escape`/Cancel returns focus to the Void trigger.

## 9. Access notes specific to this comp

- Focus ring: `2px solid accent-ink`-equivalent — dark mode uses `accent-dark oklch(0.77 0.13 290)`
  for the ring so it holds contrast against the dark substrate (the light spec's `accent-ink` value
  would under-contrast here); same `2px offset`, `:focus-visible` only. Checked against the opaque
  substrate and against the glass bar's dark-mode translucent fill at its busiest-scrolled frame,
  same method as light (`ACCESS.md` row 4).
- Skip link, landmarks (`main`/`nav`/`banner`), 44px control floor on every interactive element,
  and the terminology lock ("item," "vendor") are unchanged from light — none of those are themed.

## 10. Content direction (one line)

Same record, same numbers, same back-path fix as light — dark mode changes what the surface is
made of (a 50% glass mix instead of 60%, a re-paired Approve fill to dodge the light palette's own
borderline risk), never what it says.
