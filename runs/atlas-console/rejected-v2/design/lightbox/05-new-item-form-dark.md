# lightbox: Surface 5 of 7 — New Item Form

**Mode:** dark · **Canvas:** 1440×900 (fixed coded viewport) · **Composition anchor:**
`stacked-center` · **Background mode:** `flat-surface`

Same screen, same layout, same numbers as the light spec — only the palette and the two
declared glass art-direction values change, per this concept's own rule that the opaque data
layer is one design in two palettes while the glass command bar is two separate art
directions (lighter mix and less blur in light mode, more transparent and more legible-through
in dark mode). Nothing in the grid, the field order, the group bands, or the validation
contract differs from the light version below.

## Layout — numbers

Identical structure to the light spec (same 8px base unit, 44px control floor, same
`1440×56` command bar, `240px` left rail, `640px` centered form column at `x520–1160`, same
sequential vertical rhythm: back link → h1 "New Item" → helper line → conditional save-failure
banner → Identity band (Name*, SKU*) → Stock band (Quantity*, Reorder point*, Warehouse*) →
Sourcing band (Vendor, "+ Create vendor" inline expansion) → actions row ("Create item" /
Cancel)). Only the fills, borders, and text colors below change; every gap, padding, and
control-height number is the one already specified in
`05-new-item-form-light.md`.

- **Command bar:** dark glass token —
  `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` +
  `backdrop-filter: blur(20px)`, border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290)
  75%)`. Less opaque, more of the scrolled content reads through, per the concept's declared
  dark-mode art direction for its one glass object.
- **Left rail / main content / substrate:** `substrate` dark fill throughout, `1px solid
  hairline` (dark value) as the rail's right edge and the only band boundary.
- **Active rail row:** `accent-tint-dark` fill + 2px `accent-dark` left edge bar (shape signal
  held, color swapped for the dark-mode accent).
- **Field-group bands:** `row-alt` dark fill, same flush/no-radius/no-border treatment as light.
- **Field underlines:** `1px solid hairline` (dark), switching to the dark error hue on an
  invalid field, `2px accent-dark` on focus (paired with the standard focus ring, not
  replacing it).
- **Vendor listbox popup:** `substrate` dark fill, `1px solid hairline` (dark) border, no blur,
  no transparency — same explicit call-out as the light spec: this is the one control most
  likely to accidentally reach for the glass treatment, and it does not get it in either mode.
- **Save-failure banner:** same copy, dark error hue, `role="alert" aria-live="assertive"`,
  fields beneath it stay filled.

## Type

Identical table to the light spec — Inter Variable only, no second face, same five roles at the
same sizes/weights/line-heights. Type does not change between modes; only color does.

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| h1 (title) | Inter Variable | 20px | 600 | 28px |
| Body / field value / links / nav label | Inter Variable | 14px | 450 | 20px |
| Button label | Inter Variable | 14px | 600 | 20px |
| Field label / meta / group label / helper | Inter Variable | 12px | 450 | 16px |
| Inline error | Inter Variable | 12px | 500 | 16px |

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas / main content / rail | substrate | `oklch(0.155 0.01 290)` | text-primary | ~15:1 |
| Field-group band fill | row-alt | `oklch(0.205 0.012 290)` | text-primary / text-secondary | ~13:1 |
| Helper text, meta, group labels, hints, nav labels | text-secondary | `oklch(0.70 0.014 290)` | on substrate / row-alt | ~6:1 |
| Field underline, band-to-band boundary (decorative) | hairline | `oklch(0.33 0.014 290)` | — decorative only, never the sole boundary signal |
| Back link, "+ Create vendor" link, focus ring, active-rail bar | accent-dark | `oklch(0.77 0.13 290)` | on substrate | ~6.5:1 |
| "Create item" button fill | accent-dark | `oklch(0.77 0.13 290)` | substrate-dark text (button label rendered in near-black, `oklch(0.155 0.01 290)`, per the concept's dark-mode accent being light enough that a white label would fail — the light-mode file uses white-on-mid-accent; this dark accent is itself light, so the button's own foreground inverts to hold contrast) | ~6.5:1 estimated |
| Active-rail tint | accent-tint-dark | `oklch(0.28 0.045 290)` | accent-dark | ~5:1 |
| Inline error text + triangle glyph | error (H25, dark) | `oklch(0.65 0.17 25)` | on substrate / row-alt | ~7.5:1 — estimated, not script-verified (same RISK 4 disclosure basis as the light file) |
| Command bar (glass, the one permitted object) | glass panel (dark) | `color-mix(in oklab, oklch(0.22 0.015 290) 50%, transparent)` + `blur(20px)`, border `color-mix(in oklab, white 25%, oklch(0.3 0.02 290) 75%)` | same scrim rule, re-measured on dark per the concept's own note | flagged for build-time re-measurement |

**Note on the primary button in dark mode:** `accent-dark` (`oklch(0.77 0.13 290)`) is a light
accent by design — the concept's own dark palette never introduces a second, darker accent
value for a filled button, so "Create item" carries a dark-on-light-accent label rather than
inventing a token the spec doesn't declare. This is called out rather than silently inverted,
per the same discipline `DIRECTION.md` §7 already applies to the glass panel's two art
directions.

## Validation & state

Identical contract to the light file: blur-triggered validation only, never per-keystroke;
inline errors in the reserved 16px line per field, `role="status" aria-live="polite"`, icon +
text hue together (never color alone); nothing typed is ever discarded on a validation error or
a failed save; the save-failure banner is `role="alert" aria-live="assertive"` and the fields
beneath it stay filled; the service layer maps every Pydantic/FastAPI error to plain per-field
text before the client renders it, in both modes.

## Content direction

Identical to the light file — same placeholder-length strings, same canonical terminology
(`vendor`, `warehouse`, `item`), no invented data, no logo, no photograph. Dark mode changes no
copy, only color.
