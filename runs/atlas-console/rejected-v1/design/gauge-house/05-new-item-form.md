gauge-house: Surface 5 of 7 — New item form
=============================================

Canvas: 1440×900, full chrome, desktop tool-shaped screen. Platform mode: N/A (web/desktop-only).

Purpose: the creation flow for a new `item` (never "product/SKU") — the operator fills a
bordered, sectioned register of fields and submits without leaving the form to resolve a
missing reference (e.g. a warehouse that doesn't exist yet).

---

## 1. Layout move

Fixed viewport 1440×900.

- **Sidebar** — 240px wide, full height (0–900), substrate `oklch(0.985 0.003 58)`, 1px
  hairline right border `oklch(0.88 0.008 58)`. Nav items in this surface are inert context,
  not the subject of this comp.
- **Topbar** — full width minus sidebar (240–1440), 56px tall (y: 0–56), 1px hairline bottom
  border. Tenant/user label left, "Sign out" right, both `meta/label` role.
- **Content area** — x: 240–1440 (1200px), y: 56–900 (844px). Padding 40px on all sides →
  inner content width 1120px.
- **Breadcrumb eyebrow** — "INVENTORY / ITEMS / NEW", `section-eyebrow` role, secondary-text
  color, margin-bottom 8px.
- **Screen title** — "New item", `screen title` role, margin-bottom 24px.
- **Form column** — `stacked-center`: max-width 880px, horizontally centered in the 1120px
  inner content width (auto margins ≈ 120px either side). This is the composition anchor —
  see §5.

**Certificate panels.** The form is three bordered panels, not one long list — this is the
gauge-house layout move: each panel reads as a stamped register section, sharp corners, no
elevation.

- Panel border: 1px solid `oklch(0.88 0.008 58)`, **border-radius: 0px** (data-brutalist —
  no rounding anywhere in this comp, including inputs and the primary button).
  Four 8px L-shaped corner tick marks per panel, 1px stroke, `accent-ink` at 40% opacity —
  the blueprint surface reference.
- Panel padding: 32px.
  - Panel header row: `01` (IBM Plex Mono, identifier) + `IDENTIFICATION` (`section-eyebrow`
    role, caps), margin-bottom 16px, followed by a 1px hairline rule full panel width,
    16px gap before the first field row.
  - Panel numbers run `01 / 02 / 03` down the form.
- **Panel-to-panel gap: 24px vertical.**
- **Field grid inside a panel:** 2 columns, column-gap 32px, row-gap 24px. A field that spans
  both columns (Description) is explicitly full-width, not a 2-up row with an empty cell —
  except where the grid is intentionally held empty (Panel 03, row 2, right cell) to keep the
  module honest under an odd field count; an empty cell is a held cell, not a collapsed one.
- **Label placement:** label always above its control, never placeholder-only. `meta/label`
  role, 6px gap between label baseline and control top. Required fields append a 12px/450
  `accent-ink` asterisk with 2px left margin — `Item code *`. Optional fields carry no marker
  (7 of 12 fields here are optional, so "required" is the marked minority per the dispatch
  rule, not the reverse).
- **40px control-height floor** — every text input, select, and number input is exactly 40px
  tall; the Description textarea is 96px (still clears the floor). Control padding 10px 12px,
  1px hairline border, substrate-colored background (flat, no card fill distinct from page).
- **Focus:** `:focus-visible` only, 2px solid `accent-ink`, 2px offset — never on mouse click.

### Panel 01 — IDENTIFICATION
| Row | Left | Right |
|---|---|---|
| 1 | **Item code \*** — IBM Plex Mono input (this is the identifier). Format hint below in `meta/label`, secondary-text: `format: 3–20 chars · A–Z 0–9 -` | **Name \*** — Inter input |
| 2 (full width) | **Description** — textarea, 96px, optional | |

### Panel 02 — CLASSIFICATION
| Row | Left | Right |
|---|---|---|
| 1 | **Type \*** — select, `Select…` | **Base UoM \*** — select, `Select…` |
| 2 | **Category \*** — select, `Select…` | **Tracking mode** — select, default `None` |
| 3 | **Costing method** — select, default `—`, caption below in `meta/label`: `Leave unset to inherit the category's default.` | **Active** — checkbox, checked by default, label inline right of the box, vertically centered against the row |

### Panel 03 — STOCK PARAMETERS
| Row | Left | Right |
|---|---|---|
| 1 | **Default warehouse** — select, `Select…`, optional. Label row is `justify-between`: label left, `+ New warehouse` text-action right, 12px/600 `accent-ink`, same baseline as the label. Click expands a two-field mini-form (name + code) inline directly below the select, in place — never a route change, never a modal. Confirms into the select as the new selected value. This is the inline-creation affordance (TOOLS.md §5) | **Reorder point** — number input, IBM Plex Mono, tabular-nums. Caption below in `meta/label`: `units · integer ≥ 0` |
| 2 | **Reorder quantity** — number input, same treatment as Reorder point | *(held empty — grid discipline, not a missing field)* |

**Primary action row** — 32px margin-top below panel 03. `Create item` button (not "Save",
not "Submit"): height 44px (clears the 40px floor with CTA emphasis), padding 0 24px,
background `accent-emphasis`, white label, `body/data` weight bumped to 600 for the button
label only, 0px radius. A plain-text `Cancel` link sits 16px to its left, secondary-text
color, no border. **Enter submits the form** from any single-line field.

### The one validation error (Item code)
Fixes the live-app bug where every Pydantic error string is dumped as one block above the
title with no field association. Here, the error sits directly under the Item code input,
6px below the control — replacing the format-hint caption in that state, never stacking with
it:

> `[FLD-01]` **Item code does not meet the required format** — use 3 to 20 characters of
> letters, numbers, and hyphens.

Rendered as: input border swaps from 1px hairline to 1.5px solid error-red; the note below is
a 1px error-red bordered tag (0px radius, 4px/8px padding), `[FLD-01]` in IBM Plex Mono 12px
(it's a reference tag, i.e. an identifier), the sentence in `meta/label` role, error-red text.
This is the gauge-house move applied to failure: even a rejection reads like a stamped
non-conformance note, not a stack trace.

---

## 2. Type table

| Role | Face | Size | Weight | Line-height | Notes |
|---|---|---|---|---|---|
| Screen title | Inter Variable | 20px | 600 | 28px | "New item" |
| Section-eyebrow | Inter Variable | 12px | 600 | 16px | Caps, +0.04em tracking — breadcrumb, panel headers |
| Body/data | Inter Variable | 14px | 450 | 20px | Field values, button label (button bumped to 600 weight) |
| Meta/label | Inter Variable | 12px | 450 | 16px | Field labels, captions, hints, validation sentence |
| Identifier (Mono) | IBM Plex Mono Variable | 14px / 12px | 450 | 20px / 16px | Item code input value, panel numbers (`01`/`02`/`03`), `[FLD-01]` reference tag, Reorder point/quantity values — tabular-nums throughout. Never used for prose |

---

## 3. Paired colors, with ratios

Light mode (this comp is rendered light-only; dark tokens listed for completeness, not shown).

| Pair | Hex-equivalent role | Ratio |
|---|---|---|
| Primary text `oklch(0.20 0.01 58)` on substrate `oklch(0.985 0.003 58)` | Field values, title | **17.35:1** — computed, not rendered |
| Secondary text `oklch(0.45 0.012 58)` on substrate | Labels, captions, breadcrumb | **7.14:1** — computed, not rendered |
| Accent-ink `oklch(0.42 0.09 58)` on substrate | Required asterisk, `+ New warehouse`, focus ring, corner ticks | **8.34:1** — computed, not rendered (dispatch states 8.71:1; both clear AAA, delta is rounding/illuminant-method, not a palette error) |
| Accent-emphasis `oklch(0.55 0.13 58)` under white label | `Create item` button | **5.06:1** — matches dispatch's stated value exactly |
| Accent-tint `oklch(0.94 0.03 58)` under accent-ink text | Not used on this surface (reserved for tag/chip fills elsewhere in the set) | **7.26:1** — computed, not rendered (dispatch: 7.27:1, matches within rounding) |
| Error text `oklch(0.5 0.18 25)` on substrate | Item code validation border + note | **6.31:1** — computed, not rendered |
| Hairline `oklch(0.88 0.008 58)` on substrate | Panel borders, control borders, rules | **1.38:1** — non-text, decorative-only; no AA obligation |

All text pairings on this surface clear 4.5:1 with wide margin; the error pairing (6.31:1) and
secondary text (7.14:1) were the two worth checking by hand since neither was pre-supplied.

---

## 4. Content direction

One line: real field set carried over from the live "New item" form (Item code, Name,
Description, Type, Tracking mode, Category, Base UoM, Costing method, Active, Reorder point,
Reorder quantity), plus one new field — Default warehouse — added specifically to host the
inline-creation affordance the dispatch calls for; no invented copy beyond the one stated
validation sentence and the one stated format hint, both plausible-length and specific to this
domain.

---

## 5. Logged tokens

**Composition anchor: `stacked-center`** — the form is a single vertical run of three panels
held on-axis in the content area, with space deliberately held either side (≈120px margins
inside the 1120px content width) rather than stretched edge-to-edge. Differs from a dense
list/table surface (which would take `dense-grid`) and from a single-block auth or empty
state (which would read as `centered-statement` — this is a taller, scrollable register, not
one block).

**Background mode: `textured-surface`** — flat substrate with a faint hairline grid mesh at
very low contrast behind the panels (the blueprint reference), no photographic or gradient
element. The panels themselves stay flat (`accent-tint` and gradients are reserved for other
surfaces in this set) so the texture reads as drafting-sheet, not decoration competing with
the certificate panels.

---

## 6. Embarrassment-gate self-check

- Palette hexes/OKLCH values are quoted verbatim from the dispatch, not approximated.
- Every ratio not directly supplied by the dispatch was computed via OKLCH→linear-sRGB→WCAG
  relative luminance (script run, not eyeballed) and is marked "computed, not rendered"; two
  of three dispatch-supplied ratios were independently reproduced within 0.01–0.37 of the
  stated value, which is the check that the palette table is self-consistent.
- Both control-height (40px) and label-above-field are stated as exact numbers, not "roomy"
  or "compact."
- The one validation error is on exactly one field, in words, positioned at that field — not
  a block at the top of the form.
- IBM Plex Mono is used only where an identifier appears (item code, panel numbers, the
  reference tag, the two numeric fields) — never for the validation sentence or any label.
- No invented brand name, no logo, no fabricated data value, no lorem — copy is either carried
  from the live form's real field set or is the one stated hint/error sentence.
- Composition anchor and background-mode tokens describe what's actually specified above, not
  an aspirational upgrade.

Would sign this. Ship-ready as a spec for build.

---

## What I couldn't fully satisfy

- I don't have visibility into the other six surfaces' actual composition-anchor picks (only
  their names), so `stacked-center` is a best-guess differentiator, not a verified-unique one
  — the conductor's set-level check is the backstop here, as designed.
- The inline `+ New warehouse` affordance's expanded state (the mini name/code form and its
  own validation) is described in prose, not laid out with its own numbers — it's a
  behavior spec for the builder, not a second rendered state, since this comp is one surface
  at one moment per the one-comp rule.
- TOOLS.md §5 is referenced by the dispatch but not in my read list; the inline-creation
  pattern above is built from the dispatch's own description of it, not a citation of that
  file's exact wording.
