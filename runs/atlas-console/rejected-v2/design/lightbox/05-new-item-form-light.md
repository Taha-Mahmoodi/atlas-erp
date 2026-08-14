# lightbox: Surface 5 of 7 — New Item Form

**Mode:** light · **Canvas:** 1440×900 (fixed coded viewport) · **Composition anchor:**
`stacked-center` · **Background mode:** `flat-surface`

New Item creation. This is the screen that directly retires two confirmed live-app defects:
raw Pydantic/FastAPI validation text dumped in one top-of-page alert block, and typed input
lost on a failed validation or a failed save. Nothing here is decorative — the only job of this
comp is to prove a flat, opaque form can carry real per-field validation state without a card,
a shadow, or a floating panel doing the work instead of type and space. The one glass object
this concept allows (the floating command bar) persists across the app and is rendered here
briefly, not as this screen's subject.

## Layout — numbers

Base unit: 8px. Control floor: 44px.

- **Command bar** (persistent global chrome, kept brief — not this screen's focus): fixed,
  `0,0` to `1440×56` (7u). Glass panel per the concept's one glass token:
  `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` +
  `backdrop-filter: blur(20px) saturate(140%)`, bottom border
  `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)`. Contents: compact search input
  left-inset 16px, 320×40px, placeholder "Search or jump to…", text sits on its own scrim
  `color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)`; a single notification
  icon-button right-inset 16px, 44×44px target, 24px glyph. No quick-create control shown here
  — this screen already is quick-create, so it is omitted rather than shown disabled.
- **Left rail:** `x0–240, y56–900` (height 844). `substrate` fill, `1px solid hairline` right
  edge only — flat, opaque, no blur, per the concept's own rule that the rail is discoverability
  chrome, not the glass layer. Nav rows start `y80` (3u below the rail top), 44px row height
  each, 16px horizontal padding, 20px icon + 12px gap + 14px/450 label: Dashboard · **Items**
  (active) · Vendors · Journal Entries · Reports. Active row: `accent-tint` fill, full row width,
  no radius (flush, matches the data-layer's flat discipline), plus a 2px `accent-ink` left edge
  bar as the second, non-color signal for "active."
- **Main content:** `x240–1440, y56–900` (width 1200, height 844), `substrate` fill — the same
  opaque field as the rail and the command bar's backdrop, nothing behind the form but flat
  color. This is why the mode is `flat-surface`: no image, no gradient, no texture anywhere on
  the content layer.
- **Form column:** 640px wide, centered in the main content area —
  `x = 240 + (1200-640)/2 = 520` to `1160`. Single vertical run, space held either side — the
  `stacked-center` anchor, deliberately calmer than the dense `role="grid"` tables either side of
  it in the set.
- **Vertical rhythm**, top to bottom from the column's top edge at `y56`:
  1. `40px` (5u) top gap → **back link**: "← Back to items", 14px/500, `accent-ink`, 20px
     line-height. Targets the items list; a real link, not a JS-only handler, so it survives a
     hard refresh and screen-reader link lists.
  2. `16px` (2u) gap → **h1**: "New Item" — 20px/600, `text-primary`. The one `h1` on the
     screen.
  3. `8px` (1u) gap → helper line, 14px/450, `text-secondary`: "Fields marked * are required."
  4. **[Conditional] save-failure banner** — only rendered after a failed submit, `24px` (3u)
     gap above and below when present: `role="alert" aria-live="assertive"`, flat text line, no
     card, no icon needed beyond the sentence itself, 14px/500, error hue (`oklch(0.55 0.19 25)`
     light): *"Item wasn't created. Nothing you entered was lost — fix the highlighted fields
     and try again."* Never the raw backend string — the service layer maps every Pydantic
     error to this per-field, plain-language form before it reaches the client (defect #1's
     fix). The banner is assertive because it interrupts; the fields under it stay filled
     (defect #2's fix) — preservation and announcement priority are two different questions,
     answered separately, per the row-18 triage this concept's `ACCESS.md` pass already ran.
  5. `32px` (4u) gap → **Group 1 — Identity band**: full 640px width, `row-alt` fill (flush,
     no radius, no border — the same striping token the data tables use elsewhere in this
     concept, repurposed as a field-group separator, never as a card), `24px` (3u) padding
     top/bottom, 0 horizontal padding (flush to the column's own edges).
     - Group label "IDENTITY" — reuses the meta role (12px/450), `text-secondary`,
       `letter-spacing: 0.06em`, uppercase. Not a new type role — the concept's Inter-only
       discipline holds; this is a tracking/case treatment on the existing meta size, not a
       sixth scale step.
     - `12px` gap → **Name** — label "Name <span aria-hidden>*</span>" (12px/450,
       `text-primary`, screen-reader text appends " (required)"), `4px` gap, input full
       640px width, 44px control height, underline style: `border: none; border-bottom: 1px
       solid hairline`, no radius, transparent fill (substrate shows through), value text
       14px/450. `autofocus`. A `16px`-tall error line is always reserved directly under the
       input, empty by default — this prevents the layout jump that a validation error would
       otherwise cause, which is its own small accessibility bug if left unfixed.
     - `16px` (2u) gap → **SKU** — label "SKU *", same underline input, 4px gap below it a
       12px/450 `text-secondary` hint: "e.g. WID-1042" (a format example, not a claim). Same
       reserved 16px error line beneath.
  6. `8px` (1u) gap (substrate, between bands — the boundary signal is the color change itself,
     not a rule) → **Group 2 — Stock band**, same band treatment, label "STOCK":
     - **Quantity** — label "Quantity *", underline input, `text-align: right`, tabular
       figures — this concept's own table rows already commit to decimal-aligned tabular
       figures for numbers; a form field holding the same kind of value keeps the same
       alignment rule rather than inventing a left-aligned exception.
     - `16px` gap → **Reorder point** — label "Reorder point *", same right-aligned numeric
       input, 4px gap, hint 12px/450 `text-secondary`: "Alert when stock falls below this."
     - `16px` gap → **Warehouse** — label "Warehouse *" (canonical term, never "location"),
       native `<select>` styled to match: underline only, 16px chevron glyph inset right,
       `text-secondary`. A native select needs no app-owned popover, so it never risks
       reaching for the glass layer or a floating panel by accident.
  7. `8px` gap → **Group 3 — Sourcing band**, label "SOURCING":
     - **Vendor** — label "Vendor" (no asterisk — optional at creation; a real ERP item
       routinely exists before it has a vendor relationship), ARIA combobox pattern
       (`role="combobox"`, owns a `role="listbox"` popup), underline input, placeholder
       "Type to search vendors…" (supplementary hint, not a substitute for the visible label
       above it). The popup listbox: `substrate` fill, `1px solid hairline` border, no radius
       beyond 4px, **no blur, no transparency** — the concept reserves glass for exactly one
       object, the command bar, and a second floating surface here would be the single most
       common way this concept's own rule gets broken by accident, so it is called out
       explicitly rather than left implicit.
     - `8px` gap → **"+ Create vendor"** — text link, 14px/500, `accent-ink`. On activation,
       expands an inline flat sub-block directly below (not a modal, not a new screen — either
       would either blur the content layer or drop the in-progress item form): a 2px
       `accent-ink` left rule marks it as nested, containing "New vendor name" (underline
       input, required within this sub-block only) and a secondary "Add vendor" button
       (44px, 1px `accent-ink` outline, transparent fill, `accent-ink` label 14px/600) plus a
       "Cancel" text link. On success: the sub-block collapses, the Vendor field is populated
       with the new name, focus returns to the Vendor field, and a `role="status"
       aria-live="polite"` region (visually hidden) announces: *"Vendor '[name]' added."* No
       page navigation, no lost item-form state.
  8. `32px` (4u) gap → **actions row**: **"Create item"** — primary button, not "Save": states
     what it does. Auto width, 24px horizontal padding, 44px height, `accent-emphasis` fill,
     white label 14px/600, no radius beyond 10px. `type="submit"` on a real `<form>`, so Enter
     in any text field submits natively — no JS keydown override. `16px` gap → "Cancel" — plain
     text link, 14px/500, `text-secondary`, back to the items list.

- **Skip link:** first in DOM/tab order, visually hidden until `:focus-visible`, then fixed
  `top: 16px; left: 16px`, `accent-ink` background, white text, 14px/600, 8px/16px padding, 8px
  radius. Copy: "Skip to form" — targets the Name input.
- **Focus ring:** `2px solid accent-ink`, `2px` offset, `:focus-visible` only, on every
  interactive element (skip link, rail nav rows, command-bar search and notification button,
  every field, the vendor listbox options, both buttons, both text links). No default outline
  elsewhere.
- **Four/desktop-band equivalent:** command bar (top, fixed, reserved 56px) and left rail
  (persistent, reserved 240px) are the sticky chrome this surface owes per the `ACCESS.md`
  decision; the form column never runs under either — `y56` and `x240` are hard content
  boundaries, not visual suggestions.

## Validation & state — the two defects, closed

- **Per-field, on blur, never per-keystroke.** No live validation while typing; a field is
  checked when it loses focus, and again, for every field, on submit attempt (focus moves to
  the first invalid field on submit).
- **Error placement and channel:** inline, directly under the field, in the reserved 16px line.
  Two non-color signals together — a small solid triangle glyph (reusing this concept's own
  status vocabulary, where a solid triangle already means error/overdue) plus 12px/500 text in
  the error hue, e.g. "Name is required." / "Enter a whole number." Never a raw backend string
  ("Field required; Input should be a valid UUID…") — the service layer's Pydantic errors are
  mapped to this plain, per-field phrasing before the client ever sees them. Each error line is
  itself `role="status" aria-live="polite"` — sighted users see it in place, screen-reader users
  get it announced without an assertive interruption for routine field-level input errors.
- **Nothing typed is ever discarded** — not on a blur-triggered validation error, not on a
  failed submit. The form never resets, never clears a field, never re-renders from scratch on
  error; only the affected field's error line and the optional top banner change.

## Type

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / field value / links / nav label | Inter Variable | 14px | 450 | 20px |
| Button label | Inter Variable | 14px | 600 | 20px |
| Field label / meta / group label / helper | Inter Variable | 12px | 450 | 16px |
| Inline error | Inter Variable | 12px | 500 | 16px |

No second face anywhere on this screen, including the SKU field — the concept's own type note
for this pass is explicit that a second face would compete with the one distinction (opaque vs.
glass) that this concept exists to demonstrate, so even an identifier-shaped value stays in
Inter Variable rather than reaching for a monospace face.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / main content / rail | substrate | `oklch(0.99 0.003 290)` | text-primary | ~16:1 |
| Field-group band fill | row-alt | `oklch(0.965 0.006 290)` | text-primary / text-secondary | ~15:1 |
| Helper text, meta, group labels, hints, nav labels | text-secondary | `oklch(0.47 0.015 290)` | on substrate / row-alt | ~6.3:1 |
| Field underline, band-to-band boundary (decorative) | hairline | `oklch(0.90 0.008 290)` | — decorative only, never the sole boundary signal |
| Back link, "+ Create vendor" link, focus ring, active-rail bar | accent-ink | `oklch(0.43 0.15 290)` | on white / substrate | ~7.2:1 |
| "Create item" button fill | accent-emphasis | `oklch(0.52 0.18 290)` | white (label) | ~4.9:1 — flagged unverified (RISK 4); do not drop the label below 14px |
| Active-rail tint | accent-tint | `oklch(0.95 0.03 290)` | accent-ink | ~6:1 |
| Inline error text + triangle glyph | error (H25) | `oklch(0.55 0.19 25)` | on substrate / row-alt | ~4.8:1 — estimated, not script-verified (same disclosure basis as RISK 4) |
| Command bar (glass, the one permitted object) | glass panel | `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` + `blur(20px) saturate(140%)`, border `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)` | text scrim `color-mix(in oklab, oklch(0.98 0.01 290) 78%, transparent)` | flagged for build-time re-measurement against worst scrolled frame, per the concept's own note |

## Content direction

Real field-length placeholders only ("WID-1042", "Search or jump to…", "Type to search
vendors…"), no fabricated item data presented as if real, no invented vendor names beyond the
generic "[name]" interpolation slot in the live-region announcement. "Items," "Vendors,"
"Journal Entries" are the product's own canonical module names (`vendor`, not "supplier";
`warehouse`, not "location"), not invented labels. No logo, no photograph, no marketing copy —
the only prose on the screen is the one helper line, the one hint per field, and the one
save-failure sentence, each written at the length real copy in that slot would actually run.
