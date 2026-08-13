# chart-table: Surface 5 of 7 — New item form

Coded-comp mode. Canvas: 1440×900 fixed desktop viewport, full chrome. Platform mode: N/A (web/desktop tool-shaped screen).

**Composition anchor:** `right-rail-caption`
**Background mode:** `flat-surface`

One line: wide left field (6 of 8 grid columns) carries the form itself, the working object the grid exists to structure; the narrow right rail (2 of 8 columns) holds nothing but the single margin note — the collision made literal, not metaphorical, by putting the editorial annotation in an actual margin next to the grid it comments on. Flat cream substrate throughout, no image, no gradient — the grid and the ink are the whole surface.

---

## Layout move, with numbers

**Global chrome (persistent, shared with siblings):**
- Left nav sidebar: `0–240px` × full height `900px`. Hairline border-right `1px solid hairline`. Nav rows `40px` height (control-height floor), `16px` icon + `14px` label, `12px` left inset to icon. Items: Dashboard, Items *(active — left accent-ink bar, 2px, plus tinted row bg)*, Vendors, Customers, Warehouses, Journal entries.
- Top bar: `x 240–1440, y 0–64` (1200×64). Hairline border-bottom. Left: breadcrumb "Items / New item" (meta/label, secondary text) above title "New item" (title role, primary text). Right, right-aligned to grid edge `x=1344`: **Cancel** (secondary/ghost, `40px` height) + **Create item** (primary, `40px` height), `12px` gap between.

**Content grid (Swiss/International — the "structure" half of the collision):**
- Content area: `x 240–1440, y 64–900` → `1200×836`.
- Margins: `96px` left/right → grid runs `x 336–1344`, width `1008px`.
- 8 columns @ `105px`, 7 gutters @ `24px` → `8×105 + 7×24 = 840+168 = 1008px`. Exact, no fudge.
- **Form rail** = columns 1–6: `x 336–1086`, width `750px`.
- **Gutter**: `24px` (`1086–1110`).
- **Margin rail** = columns 7–8: `x 1110–1344`, width `234px`.
- Form top inset: `40px` below top bar → first field label baseline at `y=144`.

**Control-height floor and field spacing:**
- Every input, select, combobox, button: `40px` height floor.
- Label → field gap: `6px`.
- Field → helper/error text gap: `6px`.
- Field-group → next field-group vertical gap: `24px` (one gutter unit — spacing reuses the grid's own unit, not an invented one).
- Two-up field pairs share the `750px` row at `363px + 24px gutter + 363px = 750px`.
- Field internal padding: `12px` horizontal. Border `1px solid hairline`. Corner radius `4px` — kept tight, not soft, to stay inside the grid's own visual register.
- Required marker: `*` in **accent-ink** immediately after the label text, not in error/danger red — required is a grid fact, not a validation failure, and the two must not share a color or an operator reads "required" as "wrong."

**Field stack, in order (8 fields, real count for item creation, nothing padded in to look busy):**
1. Item name * — full width `750px`. Placeholder: "e.g. Widescreen Monitor 27in"
2. SKU * — full width `750px`. **Carries the one validation error** (see below).
3. Item type * (select: Stocked / Non-stocked / Service) — `363px`, paired with →
4. Unit of measure (select: Each / Box / kg) — `363px`
5. Warehouse * (combobox, inline-create) — full width `750px`
6. Cost price (currency, tabular-nums) — `363px`, paired with →
7. Sales price (currency, tabular-nums) — `363px`
8. Description (textarea, optional) — full width `750px`, `88px` height

**The one validation error (field 2, SKU) — inline, in words, at the field, not a top-of-form dump:**
Positioned `6px` below the SKU input, full `750px` width, meta/label size, **error/danger** color, small warning glyph `14px` at `4px` lead:
> "SKU "MON-27" is already in use by Widescreen Monitor 24in — choose a different SKU."
This names the real conflict (which item, which SKU) instead of a generic "invalid input" string. The border of the SKU field itself switches to `1px solid error/danger` while invalid; every other field keeps the hairline border. This is the fix the surface exists to demonstrate: one error, at its field, in plain words — not a raw-string list stacked above the form.

**Inline creation for a referenced entity that doesn't exist yet (field 5, Warehouse — TOOLS.md §5):**
Combobox. Typing a name with no match surfaces `+ New warehouse "West Loop"` as the last option in the dropdown, same `40px` row height, accent-ink text. Selecting it expands an inline panel directly beneath the Warehouse field — not a modal, not a route change — `1px solid hairline` bordered card, `16px` padding, containing one field ("Warehouse name", pre-filled with the typed string) and a `32px`-height "Add warehouse" button. Confirming collapses the panel, populates Warehouse with the new value, and pushes fields 6–8 back down by the panel's height. The operator never leaves the New item form.

**Submission:** Enter submits from any single-line input (not from the Description textarea, where Enter is a newline). Primary action label is exactly **"Create item"** — no "Submit," no "Save."

**Margin note (right rail, the "surface" half of the collision — sparing, one use):**
Vertically aligned to field 5 (Warehouse), `x 1110–1344`, `234px` wide. `1px solid accent-ink` left border at reduced visual weight (border only, not a filled card), `12px` left padding, no background fill — reads as an annotation, not a UI panel. Margin-serif role, **secondary text** color (a lighter hand than the form's own ink — the "penciled," not typed, correction):
> "Most items in this warehouse are non-stocked — check before saving."
Nothing else occupies the margin rail. One note, once, tied to the field it actually concerns — not a running commentary track down the side of the form.

---

## Type table

| Role | Face | Size | Weight | Line-height | Used for |
|---|---|---|---|---|---|
| Title | Inter Variable | 20px | 600 | 28px (1.4) | "New item" page title |
| Margin serif | Source Serif 4 Variable | 13px italic | 400 | 20px (1.54) | the one margin note, nowhere else |
| Body/data | Inter Variable | 14px | 450, tabular-nums | 20px (1.43) | input values, button labels, dropdown options, Cost price / Sales price |
| Meta/label | Inter Variable | 12px | 450 | 16px (1.33) | field labels, breadcrumb, required `*`, helper text, the SKU error line |

Source Serif 4 appears exactly once on this surface, at the margin note. Every other string on the screen is Inter — the rule that keeps the serif a correction rather than a second voice.

---

## Paired colors, with ratios

Oklch values are as dispatched; sRGB hex and WCAG ratios below are **computed, not rendered** — run against the substrate unless noted.

| Token | oklch | computed hex | vs substrate | Verdict |
|---|---|---|---|---|
| substrate | `oklch(0.99 0.002 58)` | `#fdfbfa` | — | base |
| primary text | `oklch(0.22 0.008 58)` | `#1e1a17` | **16.84:1** | pass, body/title text |
| secondary text | `oklch(0.46 0.01 58)` | `#5d5753` | **6.94:1** | pass, margin note + breadcrumb |
| hairline border | `oklch(0.90 0.006 58)` | `#e1ddda` | 1.31:1 | fine — border, never text |
| accent-ink | `oklch(0.40 0.07 58)` | `#643d1e` | **9.14:1** | pass, exceeds dispatched ≥7:1 — used for primary button fill, required `*`, focus ring, active-nav bar |
| accent-emphasis | `oklch(0.58 0.10 58)` | `#a66a3a` | **4.29:1** | **fails dispatched ≥4.5:1 as text on substrate** — see below |
| error/danger | `oklch(0.5 0.18 25)` | `#b32228` | **6.40:1** | pass, SKU inline error text + field border |

**accent-emphasis finding:** dispatch marked it "expect ≥4.5:1" but the computed pair lands at **4.29:1** — short of AA for normal text on the substrate. Rather than use it as small-text color anywhere on this surface, it is reserved for non-text/large-scale roles that only need 3:1 (WCAG 1.4.11 UI-component threshold): the "+ New warehouse" hover state fill and the inline-create panel's accent underline. It does not appear as body, meta, or label text on this comp. This is a palette-level finding, not a per-surface one — worth flagging back to whoever owns the palette token, since any sibling surface using accent-emphasis as text color has the same problem.

**Primary button ("Create item"):** fill `accent-ink` / label text `substrate` → same 9.14:1 pair, read in reverse. **Cancel:** `1px solid hairline` border, `primary text` label, `substrate` fill.

**Focus ring:** `2px solid accent-ink`, `2px` offset, `:focus-visible` only. On the Create item button (whose own fill is accent-ink) the 2px offset keeps the ring in the substrate gap around the button rather than on the fill itself, so it stays visible at the same 9.14:1 pair — checked, not assumed.

---

## Content direction

Copy stays functional and specific, nothing invented for texture: field labels use the exact ERP terms (Item name, SKU, Warehouse, Unit of measure), the SKU error names the real conflicting item and SKU instead of a generic string, and the single margin note is one operational tip in the navigator's voice — present because it's useful at that field, not decorating the form.

---

## Embarrassment-gate self-check

- Palette hexes as specified: yes — every token above was converted from the dispatched oklch, not substituted.
- Body-size type legible / contrast plausible at 4.5:1: yes for everything used as text (16.84:1, 6.94:1, 9.14:1, 6.40:1); accent-emphasis flagged and excluded from text use rather than shipped optimistically.
- Four bands: N/A — this is a desktop tool-shaped surface, not mobile; the desktop equivalent (sidebar nav + top bar reserved, no edge-to-edge content) is honored — top bar and sidebar are fixed chrome, form content never runs under either.
- Collision readable: yes — grid (8-col Swiss structure, hard numbers, hairline rules) vs. one serif marginalia note in the literal margin, lighter hand, one use only.
- Differs from neighbors: `right-rail-caption` / `flat-surface` are this surface's own pick, logged honestly, not nudged for variety.
- No garbled text, no invented logo, no fake superlative: none present — copy is functional labels, one specific error, one specific tip.
- Anchor/background tokens match what's actually there: yes.

**Would a designer sign this?** Yes, with the accent-emphasis caveat carried forward rather than hidden.

---

## Return

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/chart-table/05-new-item-form.md`
- **Composition anchor:** `right-rail-caption`
- **Background mode:** `flat-surface`
- **One line:** wide 6-column form rail carries the grid's structure; the 2-column right margin carries exactly one serif annotation, aligned to the field it comments on — the collision made literal rather than illustrated.
- **Unsatisfied:** `accent-emphasis` computes to 4.29:1 against the substrate, short of the dispatched ≥4.5:1 expectation for text use. Resolved on this surface by restricting it to non-text/large-scale roles (3:1 floor); not resolved at the palette level — flagging for whoever owns the token table, since it will recur on any sibling surface that reaches for accent-emphasis as body or label text.
