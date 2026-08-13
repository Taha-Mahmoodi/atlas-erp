# press-panel: Surface 6 of 7 — Empty state (filtered)

Concept: **press-panel** — data-brutalist (dominant/structure) × claymorphism (bounded/surface,
gated on restraint). Canvas: fixed 1440×900 desktop viewport. Platform mode: N/A (web/desktop
tool shell). Terminology lock: item / vendor / customer / warehouse / journal entry.

**Restraint check for this surface:** the "pending" status-pill role never appears here — zero
rows means no status pills exist to render. So this screen carries exactly **one** clay element,
not two: the "Log first item" button. That is the maximum allowed, never the minimum being
under-used; restraint intact.

---

## Composition anchor: `stacked-center`

## Background mode: `flat-surface`

One line: the eye lands on a single vertical run — headline, sub-copy, flat "Clear filters"
link, then the one clay button — held dead-center in the empty table well, with the sidebar,
top bar, and ghost column grid subordinate and unweighted around it; the whole canvas sits on
one flat, unbroken substrate with no image, gradient, or texture anywhere, so the sole
dimensional object in the frame is the clay button itself.

---

## Layout move, with numbers

**Chrome (persists across all 7 surfaces in this concept):**

| Region | Box | Notes |
|---|---|---|
| Sidebar | x:0 y:0 w:240 h:900 | 1px solid hairline border-right. Flat substrate fill, no elevation trick. |
| Top bar | x:240 y:0 w:1200 h:64 | 1px solid hairline border-bottom. Page title "Items," title/20/600, vertically centered, left-padded 24px (abs x:264). |
| Content area | x:240 y:64 w:1200 h:836 | — |

Sidebar nav rows: 48px each, left-padded 24px. Active row ("Items") is marked with a **3px
solid accent-ink** (oklch(0.40 0.10 58)) left rule and bold label weight — flat, square-cornered,
not clay. This is the concept's structural accent, kept distinct from the clay-fill accent so
the two-role gate stays legible: ink marks state, clay marks the one press-target.

**No competing CTA in the top bar on this surface.** A live app would often float a persistent
"+ New item" button top-right; it is deliberately withheld here so the clay button reads as
the unmistakable single press-target the concept promises. (Flagged below as a decision, not
an oversight.)

**Filter bar** (proves this is the *filtered*-empty variant, not true-empty): y:88 h:36, x:272.
One flat chip, square corners, 1px hairline border, meta/12/450 label + × glyph — e.g.
`Warehouse: North Dock ✕`. Not clay: chip dismissal is not the pending-status role.

**Table header** (brutalist structure holds even at zero rows): y:140 h:40, full content width
minus 32px side margins (x:272–1440). Columns, meta/12/450, uppercase, 0.04em tracking,
secondary-text color, 1px hairline border-bottom full-width:

`Item` (flex ~360px) · `Vendor` (200px) · `Warehouse` (180px) · `Qty on hand` (140px, right-
aligned, tabular) · `Unit cost` (140px, right-aligned, tabular)

**Empty well**: y:180–868 (688px tall). Vertical column-guide hairlines continue faintly
through the well at roughly 40% of the standard hairline opacity — the grid stays legible with
zero rows in it, which is the direct fix for "indistinguishable from true-empty."

**Centered stack** inside the well, all elements horizontally centered on x:840 (content-area
center), vertically centered as a block on the well's center (y:524):

| Element | y-range | Height | Type role |
|---|---|---|---|
| Headline "Nothing here yet." | 440–468 | 28px | title/20/600 |
| gap | 468–476 | 8px | — |
| Sub-copy "No items match the current filters." (max-width 360px) | 476–496 | 20px | body/14/450 |
| gap | 496–512 | 16px | — |
| "Clear filters" flat text link | 512–532 | 20px | body/14/600, accent-ink, underlined, no fill/border/shadow |
| gap | 532–564 | 32px | deliberate separation: the fix-action and the press-target must not visually compete |
| **Clay button "Log first item"** | 564–608 | 44px | clay-button/15/600 |

**The one clay button — full spec:**

- Box: height **44px** fixed (12px vertical padding + 20px line-height, top and bottom).
  Width **auto-hug**, 24px horizontal padding each side; at "Log first item" in Inter Variable
  15/600 that renders to roughly **166px** wide (min-width 160px as a floor).
- Corner radius: **16px**
- Fill: `oklch(0.60 0.14 58)` (accent-emphasis, the one dispatched clay hex)
- Label: white, 15px/600, line-height 20px, centered
- Border: **none** — the only element on the canvas with zero hairline stroke; clay reads
  through shadow, not outline, which is exactly the material's argument against the brutalist
  hairline-everywhere default around it.
- Shadow stack (claymorphism, resting state):
  - ambient: `0px 10px 24px 0px rgba(0,0,0,0.16)`
  - contact: `0px 2px 4px 0px rgba(0,0,0,0.10)`
  - inset highlight (top-left): `inset 2px 2px 3px 0px oklch(1 0 0 / 0.30)`
  - inset shadow (bottom-right): `inset -3px -3px 6px 0px oklch(0.40 0.10 58 / 0.35)` —
    reuses the dispatched accent-ink token rather than introducing a new hue
- Hover: fill darkens to `oklch(0.56 0.14 58)`
- Active/pressed: outer shadows collapse to `0px 2px 4px rgba(0,0,0,0.12)`; inset shadow grows
  to `inset 4px 4px 8px oklch(0.40 0.10 58 / 0.45)` — the button visibly presses into the clay,
  which is the one place on this screen the material pays off kinetically, not just visually.
- `:focus-visible` only: 2px solid `oklch(0.40 0.10 58)`, 2px offset, drawn outside the shadow
  stack. Never shown on pointer click.

---

## Type table

| Role | Face | Size | Weight | Line-height | Used here for |
|---|---|---|---|---|---|
| title | Inter Variable | 20px | 600 | 28px | Top-bar page title "Items"; empty-state headline "Nothing here yet." |
| body/data | Inter Variable | 14px | 450 | 20px, tabular-nums on numeric columns | Sub-copy; filter chip run-in; table body cells (n/a here, zero rows) |
| meta | Inter Variable | 12px | 450 | 16px, 0.04em tracking on labels | Table column headers; filter chip label; nav section labels |
| clay-button label | Inter Variable | 15px | 600 | 20px | "Log first item," the one clay button's label only |

No other sizes or weights appear anywhere on this surface.

---

## Paired colors, with ratios (computed, not rendered)

OKLCH → linear sRGB → WCAG relative-luminance contrast, computed via the standard OKLab
matrices (Björn Ottosson) at h=58 for every stop:

| Pair | Hexes (approx, computed) | Ratio | Verdict |
|---|---|---|---|
| primary text on substrate | `#161311` on `#F9F8F7` | **17.44:1** | passes AA/AAA body text easily |
| secondary text on substrate | `#56514E` on `#F9F8F7` | **7.34:1** | passes AA/AAA body text |
| accent-ink (focus ring / active-nav rule) on substrate | `#6E3700` on `#F9F8F7` | **8.97:1** | passes AA/AAA, also clears the 3:1 non-text floor for the focus ring and nav rule |
| hairline border on substrate | `#D4D0CE` on `#F9F8F7` | **1.45:1** | expected — this is a decorative divider/grid line, not a required UI-component boundary, so it is not held to the 3:1 non-text floor |
| **white label on clay accent (the button)** | `#FFFFFF` on `#BC670C` | **4.12:1** | **fails AA for normal text (4.5:1 floor).** 15px/600 does not clear WCAG's large-text exemption (needs ≥18.66px if bold, ≥24px if not) — see "unsatisfied" below |
| primary text on clay accent (reference only, not used) | `#161311` on `#BC670C` | 4.48:1 | also short of 4.5:1; confirms the deficit is in the accent hex, not the label color choice |

---

## Content direction

One line: copy stays flat and procedural on purpose — "Nothing here yet." / "No items match
the current filters." / "Clear filters" / "Log first item" — no adjective survives from the
sub-copy to the button label, so the single clay verb in the room is the only thing that reads
as an instruction rather than a description.

---

## Embarrassment-gate self-check

- Palette hexes present and traced back to the dispatched OKLCH values, not substituted — yes,
  every hex above is derived, not invented.
- Body-size type legible at 14/12px on a 1440×900 desktop canvas — yes, standard desktop body
  sizes, well above any mobile floor concern.
- Bands / chrome reservation (desktop equivalent) — sidebar and top bar are persistent,
  non-overlapping chrome; content area is fully below/right of both; no element bleeds under
  either.
- Collision readable — brutalist structure (hairline grid, square corners, flat chips, ink-rule
  active state) dominates the frame; claymorphism appears exactly once, on the one CTA, and
  nowhere else, matching the two-role gate (the second role, the pending pill, is correctly
  absent because there are zero rows to carry it).
- Composition differs from neighbors — this is the only surface in the set built as a centered
  empty-well stack rather than a populated table or form; distinct from items-list (dense-grid,
  populated) and from a login/form surface by construction.
- No garbled text, no invented logo, no hollow superlative — copy list above is exhaustive and
  plain; no brand mark invented for the sidebar wordmark region (left unspecified/generic here
  since no real product name was supplied in the dispatch).
- Anchor/background tokens match what's actually described — `stacked-center` is the literal
  vertical run in the well; `flat-surface` is accurate, nothing behind the content but the one
  substrate.

**Would a designer put their name on this?** Yes, with the one caveat below flagged rather than
silently shipped.

---

## Returned

- **Comp path:** `/Users/taha/Documents/atlas-erp/runs/atlas-console/design/press-panel/06-empty-state.md`
- **Composition anchor:** `stacked-center`
- **Background mode:** `flat-surface`
- **One line:** a single centered vertical stack in an otherwise-populated table frame — the
  grid header and faint column guides stay onscreen to prove this is "filtered," not "empty,"
  while every neighboring surface (items-list, vendor-bill-detail, new-item-form) is a
  populated dense-grid or form layout instead.
- **Unsatisfied:**
  1. **White-on-clay button label computes to 4.12:1**, below the 4.5:1 AA floor for 15px/600
     text (which does not clear the large-text exemption). This is a property of the dispatched
     accent-emphasis hex `oklch(0.60 0.14 58)` paired with white, not a choice made on this
     surface — flagging for Loop 1/DIRECTION.md rather than substituting a different hex myself.
     Two non-destructive fixes exist if wanted: darken the button-only fill a few percent L, or
     move the label to accent-ink `oklch(0.40 0.10 58)` on a lighter clay tint — either clears
     4.5:1 without touching the dispatched accent-emphasis token used elsewhere.
  2. Deliberately withheld the top-bar "+ New item" button that a live tool-shaped app would
     normally show persistently, so the one clay CTA reads as unambiguous. Worth confirming
     this reads as intentional restraint and not a missing affordance when Gate A sees it next
     to items-list (surface 3), where that top-bar action presumably does appear.
