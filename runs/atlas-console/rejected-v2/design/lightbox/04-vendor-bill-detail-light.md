# lightbox: Surface 4 of 7 — Vendor Bill Detail
**Mode:** light · **Canvas:** 1440×900 fixed viewport, coded spec, full chrome · **Platform:** web/desktop-only

**Composition anchor:** `right-rail-caption` — wide left field (the line-items grid) carries the
record's real content; a narrower right rail holds the document-flow chain as inspector/detail
metadata, exactly what the token describes.

**Background mode:** `flat-surface` — one solid opaque substrate (`oklch(0.99 0.003 290)`) under
everything except the one glass object. No image, no gradient, no texture: the concept's entire
argument is that the data layer has nothing behind it but itself.

---

## 1. Region map (top to bottom, viewport-relative y)

| Region | y-range | Height | Notes |
|---|---|---|---|
| Glass command bar (fixed) | 0–64 | 64px | Only glass object on screen. Persists above scroll. |
| Content top padding | 64–88 | 24px | 8px-unit rhythm (3×8). |
| Back link | 88–132 | 44px hit zone | First thing on screen, plain text, not a button. |
| H1 + status pill | 148–176 | 28px | `Vendor Bill BILL-2026-00003`, title role. |
| Metadata row (vendor / amount / due date) | 192–232 | 40px | Three fields, tabular values. |
| Actions row (Approve / Void) | 256–300 | 44px | Plain flat buttons, 12px gap. |
| Main split: line-items grid (left) + document-flow rail (right) | 332–648+ | variable, scrolls | 900-col grid col / 32px gutter / 444-col rail. |

Content column: 32px side margins → usable width 1376px (1440 − 64). Left field 900px, gutter
32px, right rail 444px (900 + 32 + 444 = 1376).

## 2. Glass command bar (per §7, same spec as surfaces 2/3 — kept brief here)

- Fixed, full-width, height 64px, `z-index` above all content.
- Fill: `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)`, `backdrop-filter: blur(20px)
  saturate(140%)`, border-bottom `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)`.
- Every text run on the bar sits on its own scrim: `color-mix(in oklab, oklch(0.98 0.01 290) 78%,
  transparent)`, measured against the busiest row scrolling underneath (RISK 1, flagged for
  build-time re-measurement, not assumed passing).
- Contents on this screen: search field (placeholder "Search or jump to…"), record-number jump
  target already resolved (user is already on BILL-2026-00003). No quick-create needed on a
  detail screen — omitted rather than padded in.
- Reserved-space, not floating-over: content below starts at y=64 in normal flow. On scroll, prior
  content passes underneath/behind the bar and reads through the blur — that is the only place
  anything is ever seen "through" the glass on this screen.

## 3. Back link (fixing the confirmed defect: no breadcrumb, no back-nav today)

- Plain flat text link, **not a button**: `← Back to Vendor Bills`.
- First element in the content flow, directly under the glass bar, before the H1.
- Body/data role, 14px/450, color `accent-ink oklch(0.43 0.15 290)` (~7.2:1 on substrate) so it
  reads as interactive without any chrome. Underline on `:hover`/`:focus-visible` only.
- Sits inside a 44px-tall click/tap zone (control floor) even though the visual line is 14px —
  padding, not a visible box.
- Also the skip-link's landmark target order: skip link (visually hidden, first in DOM/tab order,
  visible on focus) lands on `#main-content`, which starts at the H1 below, per row 9 of
  `ACCESS.md` — the back link is reachable by continuing Tab from there.

## 4. Title + bill status

- `<h1 id="main-content" tabindex="-1">Vendor Bill BILL-2026-00003</h1>` — title role, 20px/600,
  `text-primary oklch(0.20 0.012 290)`. One `h1` per screen, per row 9.
- Inline status: half-filled/striped circle, hue 80° (pending), 16px, immediately right of the H1,
  with visible text label "Pending approval" (14px/450) — shape + text, never color alone.
- On SPA route-entry, focus moves programmatically to this `h1` (`tabindex="-1"`), per row 13.

## 5. Metadata row

Three fields, left-aligned as a row, 32px gaps between fields:

| Field | Label (12px/450, `text-secondary`) | Value (14px/450 tabular, `text-primary`) |
|---|---|---|
| Vendor | "Vendor" | Meridian Office Supplies |
| Amount | "Amount" | $1,874.34 (right-aligned, decimal-aligned) |
| Due date | "Due date" | 2026-04-11 (Net 30 from bill date 2026-03-12) |

"Vendor" — never "supplier," per terminology lock.

## 6. Actions row

- **Approve** — plain flat button, `accent-emphasis` fill `oklch(0.52 0.18 290)`, white text
  (~4.9:1, borderline — held at 16px/600 per the palette's own stated floor for this pairing).
  44px height, 20px horizontal padding, no shadow, no gradient.
- **Void** — plain flat button, hairline border `oklch(0.90 0.008 290)`, `text-primary` fill-less
  interior, 44px height, 12px gap from Approve. Opens the void confirmation modal (§8).
- Both buttons are content-layer, opaque — no glass touches this row.

## 7. Left field — line-items grid (`role="grid"`)

- Header row (y≈332–364, 32px): `Item` · `Qty` · `Unit price` · `Line total` — meta role, 12px/450,
  `text-secondary`, bottom hairline `oklch(0.90 0.008 290)`. `Item`, never "product" or "SKU."
- 5 data rows, 40px each, tabular-nums, right-aligned + decimal-aligned on every money column.
  Zebra banding on even rows: `row-alt oklch(0.965 0.006 290)`. Hairline divider between every row.

| Item | Qty | Unit price | Line total |
|---|---:|---:|---:|
| A4 Copy Paper, 80gsm | 200 | $4.20 | $840.00 |
| Toner Cartridge — Black | 12 | $38.50 | $462.00 |
| Desk Organizer Tray | 30 | $9.75 | $292.50 |
| Whiteboard Markers (Pack of 12) | 15 | $6.40 | $96.00 |
| Shipping & Handling | 1 | $45.00 | $45.00 |

- Summary block below the grid (not part of `role="grid"`, a plain content block): Subtotal
  $1,735.50 · Tax (8%) $138.84 · **Total $1,874.34** — total in body/data 14px/600-weight-not-
  defined, so held at 14px/450 with `text-primary` and a top hairline rule instead of added weight,
  per the concept's own "hierarchy from type and space alone."
- Keyboard/ARIA contract (row 14): arrow keys move cell focus, Enter/Space activate a cell,
  Shift+arrow extends selection where applicable. No inline-editable cells on this read-mostly
  screen, so no entered-cell widget state is needed here.
- Row-deleted focus fallback (row 13) is inherited from the pattern, not exercised on this screen
  (line items aren't deleted from the detail view).

## 8. Right rail — document-flow chain (PO → GRN → Bill)

Plain vertical list. No cards, no shadow, no ornamentation — a 1px hairline connector runs down
the left edge between dots (structural, not decorative, same register as the grid's own hairlines).

| Stage | Record | Date | Checked by | Dot | Accessible name |
|---|---|---|---|---|---|
| Purchase Order | PO-2026-00081 | issued 2026-03-02 | J. Alvarez | solid circle, H150 | "Approved — PO, checked 02 Mar" |
| Goods Receipt | GRN-2026-00114 | received 2026-03-09 | T. Osei | solid circle, H150 | "Approved — GRN, checked 09 Mar" |
| Vendor Bill | BILL-2026-00003 (this record) | entered 2026-03-12 | — awaiting review | half-filled/striped circle, H80 | "Pending approval — Bill, awaiting review" |

- Each dot is the accessible element (e.g. `<span role="img" aria-label="…">`) carrying the full
  name above — dots are never `aria-hidden`, per the task's own naming pattern.
- Stage label 14px/450, record number + date + checked-by 12px/450 `text-secondary`, tabular for
  the date.
- Shape vocabulary (fixed across the whole concept, restated here for this screen): solid filled
  circle = posted/approved (H150) · outlined circle = draft (unused on this record) · half-filled/
  striped circle = pending (H80) · solid triangle = error/overdue (H25, unused on this record).

## 9. Void confirmation modal

- Trigger: Void button (§6). Overlay: flat solid scrim, `oklch(0.20 0.012 290 / 0.4)`, **no blur** —
  per the concept's own rule that a decision worth conflict/confirmation "never gets blurred."
- Panel: opaque `substrate`, 1px hairline border, no shadow, 400px wide, centered, 24px padding.
- Heading (h2, reuses title role 20px/600): "Void this bill?"
- Body (14px/450, `text-secondary`): "This can't be undone. BILL-2026-00003 will be marked void
  and removed from the payable balance."
- Buttons: **Cancel** (plain flat, hairline border) and **Void** (plain flat, hairline border,
  `text-primary` — not `accent-emphasis`; fill is reserved for Approve alone, per the brief).
- **Focus contract** (`ACCESS.md` row 16): initial focus lands on **Cancel** on open (least-
  destructive action). Focus trapped in the dialog. `Escape` or Cancel closes and returns focus to
  the Void trigger button. Invoker-gone fallback: focus to the next row, or the table itself if now
  empty — inherited, not exercised on this single-record screen.

## 10. Access notes specific to this comp

- Skip link: visually hidden, first in DOM/tab order, visible on `:focus-visible`, targets
  `#main-content` (the `h1`, §4).
- Landmarks: one `main`, one `nav` ("Primary," the left rail, unglassed per concept), one `banner`.
- Focus ring: `2px solid accent-ink`, `2px offset`, `:focus-visible` only. Checked against the
  opaque substrate (back link, actions, grid, rail — all pass at the same ratio as the token
  itself, ~7.2:1) **and** against the glass command bar's translucent fill at its busiest-scrolled
  frame, since the search field inside the bar is the one focusable control that ever sits on
  glass on this screen (`ACCESS.md` row 4).
- Every control on this screen clears the 44px floor: back link hit zone, Approve, Void, modal
  Cancel/Void, and the command-bar search field.
- Terminology lock held throughout: "item" (grid header, never "product"/"SKU"), "vendor" (never
  "supplier").

## 11. Content direction (one line)

Real numbers that add up (line items sum to the stated total, tax computed, not invented), a real
document-flow chain with two already-posted predecessors and one pending current stage, and a
first-ever back path on a screen that currently ships without one — the fix is the headline, not
a footnote.
