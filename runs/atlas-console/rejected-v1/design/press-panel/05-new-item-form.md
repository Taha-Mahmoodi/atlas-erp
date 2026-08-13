# press-panel: Surface 5 of 7 — New item form

**Canvas:** 1440×900 fixed viewport, tool-shaped desktop, full chrome (top bar + left nav rail + content).
**Platform mode:** N/A (desktop web).
**Composition anchor:** `dense-grid`
**Background mode:** `flat-surface`

## Layout move

The collision's whole argument is that a flat instrument panel reads as calm because
nothing on it competes for the hand — so this comp draws thirteen nav rows, seven field
rows, and one textarea in perfectly flat, sharp-edged, hairline-bordered controls, and
reserves the entire vocabulary of depth (rounded corners, dual shadow, lift) for exactly
one object: the **Create item** button. The "pending" status pill, this concept's other
licensed clay role, does not appear on this surface at all — a creation form has no rows
with status — which is itself the honest reading of the restraint rule, not a gap to fill.

**Numbers used everywhere on this surface:**
- **40px** — control-height floor for every flat input (text field, select, textarea's
  label row is exempt but the *field* controls hold it)
- **24px** — vertical gap between field rows
- **32px** — horizontal gutter between the two field columns
- **2px** — corner radius on every flat control (field borders, nav active-state
  indicator's fill, the inline warehouse-creation affordance)
- **160×44px, 12px radius** — the one clay button. Taller than the 40px flat floor and an
  order of magnitude more rounded than the 2px flat radius — the jump in radius is the
  signal, not a color

```
0,0 ─────────────────────────────────────────────────────────────────── 1440,0
│ TOP BAR — reserved, y 0–56, full width, never overlapped                │ h=56
│ "ATLAS ERP"(title role, x=24, v-center)   "owner@acme.test"  "Sign out" │
│                                             (meta, secondary/accent-ink,  │
│                                              right-aligned, ends x=1416) │
│ ── 1px hairline, full width, y=56 ──                                    │
├──────────────┬──────────────────────────────────────────────────────────┤ y=56
│ NAV RAIL      │ CONTENT — x 224–1440 (w=1216), y 56–900 (h=844)          │
│ x 0–224       │                                                           │
│ y 56–900      │  padding 40px → active column x 264–1400, y starts 88   │
│ (w=224,h=844) │                                                           │
│ 1px hairline  │  "New item" — title role, x=264, y 88–116        h=28   │
│ right border  │  +32                                                     │
│               │  ┌─ col A, x264–664 (400) ─┐  ┌─ col B, x696–1096(400)─┐ │
│ 13 flat rows, │  │ ROW 1  y148–228 (h80,    │  │ ROW 1  y148–208(h60)   │ │
│ 40px each,    │  │ error present)           │  │                        │ │
│ starting y=80:│  │ Item code* — label 12/450│  │ Name* — label 12/450   │ │
│ Home          │  │  y148–164                │  │  y148–164              │ │
│ Finance       │  │ [field 400×40, hairline, │  │ [field 400×40]  y168–  │ │
│ Inventory ▮   │  │  2px radius]  y168–208   │  │  208                   │ │
│  (active: 3px │  │ "Item code is required." │  │                        │ │
│  accent-ink   │  │  meta 12/450, error color│  │                        │ │
│  left bar +   │  │  y212–228                │  │                        │ │
│  flat 8%-tint │  ├───────────────────────────┴────────────────────────┤ │
│  fill, 2px    │  │ ROW 2  y252–360 (h108) — full width, x264–1096(832) │ │
│  radius, NOT  │  │ Description — label 12/450  y252–268                │ │
│  clay)        │  │ [textarea 832×88, hairline, 2px radius] y272–360     │ │
│ Procurement   │  ├───────────────────────────┬────────────────────────┤ │
│ Sales         │  │ ROW 3  y384–444 (h60)     │  ROW 3  y384–444 (h60) │ │
│ Manufacturing │  │ Type* — label, [select    │  Category* — label,    │ │
│ Quality       │  │  400×40]                  │  [select 400×40]       │ │
│ Maintenance   │  ├───────────────────────────┼────────────────────────┤ │
│ HR            │  │ ROW 4  y468–548 (h80,     │  ROW 4  y468–528 (h60) │ │
│ Projects      │  │ inline-create present)    │                        │ │
│ CRM           │  │ Default warehouse* —      │  Base UoM* — label,    │ │
│ Reporting     │  │  label 12/450 y468–484    │  [select 400×40]       │ │
│ Admin         │  │ [select 400×40, "Select…" │                        │ │
│ (all meta     │  │  ] y488–528               │                        │ │
│  12/450,      │  │ "+ New warehouse" —       │                        │ │
│  primary text,│  │  meta 12/450, accent-ink, │                        │ │
│  flat, no clay│  │  flat text trigger, no    │                        │ │
│  anywhere in  │  │  border/fill  y532–548    │                        │ │
│  the rail)    │  ├───────────────────────────┼────────────────────────┤ │
│               │  │ ROW 5  y572–632 (h60)     │  ROW 5  y572–632 (h60) │ │
│               │  │ Tracking mode — [select]  │  Costing method —      │ │
│               │  │                            │  [select 400×40]       │ │
│               │  ├───────────────────────────┼────────────────────────┤ │
│               │  │ ROW 6  y656–716 (h60)     │  ROW 6  y656–716 (h60) │ │
│               │  │ Reorder point — [field,   │  Reorder quantity —    │ │
│               │  │  tabular-nums]             │  [field, tabular-nums] │ │
│               │  ├───────────────────────────┴────────────────────────┤ │
│               │  │ ROW 7  y740–780 (h40) — Active                     │ │
│               │  │ [20×20 checkbox, flat, 2px radius] + "Active"      │ │
│               │  │  label (body role) — full row is a 40px click/     │ │
│               │  │  tap target even though the visual box is 20px     │ │
│               │  ├──────────────────────────────────────────────────┤ │
│               │  │ ROW 8  y804–848 (h44) — action row                 │ │
│               │  │ [CLAY — Create item, 160×44, 12px radius, dual     │ │
│               │  │  emboss shadow, accent-emphasis bg, white label]   │ │
│               │  │  x264–424, y804–848                                │ │
│               │  │ "Cancel" — flat text link, body role, secondary-   │ │
│               │  │  text, x=440, y816–836 (v-centered on button)      │ │
│               │  └──────────────────────────────────────────────────┘ │
│               │  content ends y=848; 52px unused margin to canvas     │
│               │  bottom (900) — held, not stretched to fill            │
└──────────────┴──────────────────────────────────────────────────────────┘
```

**Fixed working width, not stretched:** the two-column field grid is 832px wide
(400+32+400), left-aligned inside a 1136px-wide available content band — 304px of
right margin is held empty rather than stretching fields full-bleed. Same fixed-width
instrument-panel choice this concept's login surface made with its 400px column; a
brutalist panel has an honest working size, it doesn't rubber-band to fill the glass.

**The one clay object, in full:** `Create item`, 160×44px, background
`accent-emphasis oklch(0.60 0.14 58)`, white label (clay-button role, 15px/600),
12px corner radius, dual box-shadow —
`4px 4px 8px oklch(0.40 0.10 58 / 0.35)` (dark, lower-right, using accent-ink as the
shadow tint) and `-3px -3px 6px oklch(1 0 0 / 0.55)` (light, upper-left) —
*(both shadow values invented for this comp, modeled on the standard claymorphic
dual-shadow recipe scaled to a 44px control; computed, not rendered)*. Focus ring:
2px solid accent-ink, 2px offset, drawn outside the emboss shadow so it never gets
visually absorbed into the soft edge — same ring spec as every flat control on the
page, per the dispatch's global rule.

**Inline creation (TOOLS.md §5):** `Default warehouse*` renders as a normal flat
40×400 select reading "Select…" with a flat text trigger, "+ New warehouse", directly
beneath it (row 4, col A) — clicking it does not open a modal or leave the form; it
expands the same 400px column into a flat inline text field ("Warehouse name") with
two small flat text actions, "Add" / "Cancel", pushing rows 5–8 down by the expanded
block's height. No clay anywhere in this pattern — inline creation is a flat
interaction, same register as the rest of the panel, not a second CTA competing with
the one at the bottom of the form.

**The one inline error:** `Item code*` is the single field shown with a live
validation error, in words, directly beneath its own field — "Item code is required."
— flat 12px/450 text in the error token, never a chip, never clayed. This replaces the
live app's top-of-form concatenated-Pydantic-string dump (`CURRENT.md` §9) entirely;
per TOOLS.md §5 it fires on blur, not per keystroke, and is announced to assistive
tech at the point of the field, not the top of the page.

## Type table

| Level | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| title (`New item`, `ATLAS ERP` wordmark) | Inter Variable | 20px | 600 | 28px (1.4) |
| body/data (field values, `Active` label, `Cancel` link, select text, reorder point/quantity) | Inter Variable, tabular-nums on numeric fields | 14px | 450 | 20px (1.43) |
| meta/label (field labels, required asterisk, error text, `+ New warehouse` trigger, nav rail rows, top-bar identity/sign-out) | Inter Variable | 12px | 450 | 16px (1.33) |
| clay-button label (`Create item`, the one clay object) | Inter Variable | 15px | 600 | 20px (1.33) |

No fifth role invented. Chrome text — the wordmark, the thirteen nav rows, the
top-bar identity strip — is pressed into the same four roles the form itself uses;
holding the type system to exactly what the dispatch gave is this comp's small echo
of the restraint the palette enforces on clay.

## Paired colors, at used size

*(Freshly computed for this comp's exact tokens via OKLCH → linear-sRGB → WCAG
relative-luminance conversion, not eyeballed — all six flagged **computed, not
rendered**.)*

| Pair | Where used | Ratio |
|---|---|---|
| primary text `oklch(0.19 0.006 58)` on substrate `oklch(0.98 0.002 58)` | field values, checkbox label, "New item" title, wordmark | **17.44:1** *(computed, not rendered)* |
| secondary text `oklch(0.44 0.008 58)` on substrate | field labels, nav rows, top-bar identity, Cancel link | **7.34:1** *(computed, not rendered)* |
| accent-ink `oklch(0.40 0.10 58)` on substrate | "+ New warehouse" trigger, active-nav left bar, Sign out link, focus ring | **8.97:1** *(computed, not rendered)* |
| white on accent-emphasis `oklch(0.60 0.14 58)` | "Create item" clay button label | **4.12:1** *(computed, not rendered — see "couldn't fully satisfy")* |
| error `oklch(0.5 0.18 25)` on substrate | "Item code is required." inline text, required asterisk | **6.22:1** *(computed, not rendered)* |
| hairline border `oklch(0.86 0.005 58)` on substrate | field borders, textarea border, nav rail divider, top-bar divider | **1.45:1** *(computed, not rendered — see "couldn't fully satisfy")* |

## Content direction

The form speaks entirely in real Atlas item-record fields (`CURRENT.md`'s `form-item.png`
inventory: item code, name, description, type, category, base UoM, tracking mode,
costing method, active, reorder point, reorder quantity) plus one new field, `Default
warehouse*`, added specifically to carry the dispatch's inline-creation demonstration —
placed next to `Base UoM*` because both configure where and how the item is tracked, not
inserted at random. No invented data, no lorem, no fabricated numbers presented as real
stock — every label on the panel is a field Atlas ERP's schema actually has or would
plausibly add under the same terminology lock (item / vendor / customer / warehouse /
journal entry).

## Self-check (embarrassment gate)

**Restraint-rule audit — every element on the screen, clay or flat:**

| Element | Treatment |
|---|---|
| Create item button | **CLAY** — the form's one confirming action, per dispatch |
| Nav active-state indicator (Inventory) | flat — 8% accent-ink tint fill + 3px solid left bar, 2px radius, no shadow |
| All 13 nav rows | flat |
| All field borders (text, select, textarea) | flat — hairline, 2px radius |
| "+ New warehouse" trigger | flat text, no border, no fill |
| Checkbox (Active) | flat — 20×20, 2px radius, no shadow |
| Cancel | flat text link |
| Error text | flat, error token, never a chip |
| Status pills | **absent** — this surface has none; the concept's second clay role isn't forced onto a screen that has no status to show |

Exactly one clay object on the canvas. Nothing else carries a shadow or a radius
above 2px. That is the whole test of the collision sentence and it holds.

Read back against the palette table: all six pairs used on this surface are present
above with their own freshly computed ratios (not copied from a sibling surface's
numbers, since this comp's substrate/text values differ slightly from `01-login`'s —
0.98/0.19/0.44 here vs. 0.985/0.20/0.45 there). 40px flat-control floor holds on
every field, select, and the button (44px, above floor). 24px row gap and 32px
column gutter are constant everywhere they're claimed. Both bands (top bar 56px,
nav rail 224px) are reserved and never overlapped by content. Required marking uses
the error token consistently (asterisk + inline text, never color alone — text is
present). No fabricated tenant data beyond the existing seed placeholder pattern
(`owner@acme.test`, already the live app's own seed value). Would put a name on this.

## Couldn't fully satisfy

Two token pairs given in the dispatch's palette fall under commonly-cited contrast
floors, and both are inherited constraints, not choices made on this surface:

1. **White label on `accent-emphasis`, 4.12:1** — under the 4.5:1 AA floor for normal
   text, and the button label (15px/600) is not large enough by WCAG's own large-text
   definition (18.66px bold minimum) to drop to the 3:1 large-text floor either, even
   though 4.12 clears that lower number. This is the exact token and role the dispatch
   specified ("accent-emphasis … white label [mark computed]"), so it's flagged here
   as the one clay button on the one surface that renders it, rather than silently
   passed through.
2. **Hairline border on substrate, 1.45:1** — well under the 3:1 WCAG 1.4.11 floor for
   a required UI boundary (field edges, textarea edge, thirteen nav-row dividers all
   use this pair). Same inherited value the `01-login` sibling flagged against the
   same floor.

Worth a Loop 1 palette check on both before this comp's numbers ship past Gate A —
neither is a decision this surface can make on its own since both colors are given,
not chosen, here.
