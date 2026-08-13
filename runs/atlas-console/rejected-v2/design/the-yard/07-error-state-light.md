# the yard: Surface 7 of 7 — Error State (Record Not Found)
**Mode:** Light · **Canvas:** 1440×900 fixed desktop viewport · Web/desktop-only · Coded-comp spec

Fixes the confirmed live-app bug: navigating to a non-existent/malformed item record ID
currently renders a silently-blank "Edit item" form (every field empty, indistinguishable
from a just-reset form; the real 422 sits in devtools). This screen replaces that blank form
with a stated, announced error and a way back — nothing else on the route changes.

---

## 1. Layout — 1440×900

Persistent app chrome stays mounted; only the record-detail content region shows the error.
No dense grid, no lane cards on this surface — this is the one deliberately calm, low-content
screen in the set, matching surface 6 (empty state) and standing apart from the dense-grid
list/detail screens (03, 04).

| Region | Bounds (x, y, w, h) | Content |
|---|---|---|
| Left rail | `0, 0, 240, 900` | Persistent nav, icon+label at rest (canvas is under the 1600px reveal breakpoint, rail does not widen). Role-derived order, most-frequent module first. **Items** shown active/current — this error originated from an items-detail route |
| Sticky header | `240, 0, 1200, 56` | `space-sticky = 56px`, reserved layout space, never floats. Breadcrumb `Items / Item not found` (Items is a link, text-secondary → accent-ink on hover/focus; "Item not found" is current-page, text-primary, not a link) left-aligned at 24px inset. ⌘K command-palette trigger pill, right-aligned at 24px inset |
| Content area | `240, 56, 1200, 844` | Substrate fill. Holds the centered card |
| Error card | `560, 273, 560, 410` | Centered within the content area both axes: `(1200-560)/2 = 320` from the rail edge, `(844-410)/2 = 217` below the header |

**Composition anchor: `centered-statement`.** One block — the torn token + message — sits on
the canvas axis; the rail and header are present and functional but visually subordinate,
rendered at rest with no competing content, no second card, no metric numbers anywhere on
this screen.

**Background mode: `flat-surface`.** Single flat substrate fill behind rail, header, and
content; the card is one more flat asset sitting on it. No gradient, no image, no texture —
the calm register this screen is built for.

### Error card — internal stack (padding 64px, content column 432px wide, all centered)

| Y-range | Element | Spec |
|---|---|---|
| 64–160 | Torn signal-token | 96×96px, see §3 |
| 160–184 | gap 24px | — |
| 184–212 | `<h1>` "Item not found" | title 20px/600, text-primary, centered |
| 212–224 | gap 12px | — |
| 224–244 | Body message | "This record wasn't found. Nothing was changed." body/data 14px/450, text-secondary, centered, max-width 400px (wraps, not fixed-box) |
| 244–252 | gap 8px | — |
| 252–270 | Meta identifier line | "Item ID from the link:" meta 12px/450 text-secondary + `ITM-2026-00417` mono-identifier 13px/500 JetBrains Mono, text-secondary — echoes the malformed/unresolved param, not a data claim |
| 270–302 | gap 32px | — |
| 302–346 | "Back to items" button | 44px height floor, see §4 |
| 346–410 | padding 64px | — |

Card container: `card` token fill, `border-radius: 24px`, 1px `hairline` border (decorative
only, paired with the shadow, never the sole boundary per `§10`) + soft drop shadow
(`0 8px 24px -8px oklch(0.21 0.015 290 / 0.16)`). No glass, no blur, no hard edges — consistent
with the concept's "rounded corners throughout, soft drop shadows, no glass" rule.

---

## 2. Type table

| Level | Face | Size / Weight | Line-height | Used for |
|---|---|---|---|---|
| title | Inter Variable | 20px / 600 | 28px | `<h1>` "Item not found" |
| body/data | Inter Variable | 14px / 450 | 20px | Error message sentence |
| meta | Inter Variable | 12px / 450 | 16px | "Item ID from the link:" label |
| mono-identifier | JetBrains Mono Variable | 13px / 500 | 16px | `ITM-2026-00417` — ligature-free tabular digits, never mistaken for prose |
| button-label (deviation) | Inter Variable | 16px / 600 | 20px | "Back to items" — sized up from the run's usual button scale specifically to clear the accent-emphasis contrast floor, see §4 |

---

## 3. Torn signal-token

The one atomic status unit in this concept, in a state that exists nowhere else in the run:
every other token (draft/pending/posted/overdue/closed) keeps a clean rounded-rectangle or
pill edge. This is the only token with a broken edge, and it never appears at small/inline
size — it is the primary visual anchor of the whole screen.

- **Base shape:** 96×96px squircle, `border-radius: 28px` on the intact corners
- **Fill:** Overdue/Error hue, `oklch(0.55 0.19 25)`
- **Torn edge:** the bottom-right ~35% of the shape is cut away along a jagged 5-vertex zigzag
  path (clip-path polygon, teeth roughly 8–14px deep, irregular — not a repeating pattern),
  exposing the card fill behind it. This is the sole differentiator from every clean-edge
  token elsewhere in the concept and must not be softened into a rounded notch
- **Glyph:** white exclaim mark, Inter Variable 700, ~32px, optically centered in the intact
  upper-left two-thirds of the shape so the tear never clips it
- **Accessible name:** visually-hidden text, `"Error — item record not found"`, following the
  concept's naming pattern (state + record) even though no specific record resolved

---

## 4. Palette — light (from DIRECTION.md §6)

| Token | Value | Role here | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | content-area fill, rail fill | text-primary | ~15:1 |
| card | `oklch(1 0 0)` | error card fill | text-primary | ~16:1 |
| text-primary | `oklch(0.21 0.015 290)` | h1, breadcrumb current | on card/substrate | ~16:1 / ~15:1 |
| text-secondary | `oklch(0.46 0.02 290)` | body message, meta label, mono ID, breadcrumb link | on card | ~6.5:1 |
| hairline | `oklch(0.89 0.01 290)` | card border — decorative only, paired with shadow, never sole boundary | — | sub-3:1, non-load-bearing |
| accent-ink | `oklch(0.44 0.15 290)` | breadcrumb-link hover/focus color, focus ring | white / on card | ~7:1 |
| accent-emphasis | `oklch(0.53 0.18 290)` | "Back to items" button fill | white `oklch(1 0 0)` | ~4.8:1 — borderline; **only used here because the label is set to 16px/600**, clearing the run's stated large-text floor for this token pair (`§8 RISK 4`) |
| accent-tint | `oklch(0.94 0.035 290)` | not used on this screen (no tinted state to show) | — | — |
| Overdue/Error hue | `oklch(0.55 0.19 25)` / white glyph | torn token fill | white | per concept status table |

---

## 5. Access

- **Landmark structure:** skip link ("Skip to main content", visually hidden until `:focus`,
  first in tab order) → left rail nav → header → `<main>` containing the error card. One `<h1>`
  on the page: "Item not found"
- **Live region:** the error card's title+message block (h1 + body message, not the meta line,
  not the button) is wrapped in `role="alert" aria-live="assertive"`, per this run's imperative
  tier — the operator was expecting a record and got nothing, this is not advisory
- **Focus on load:** the alert wrapper carries `tabindex="-1"` and receives programmatic focus
  on mount. This is the second channel called for in `ACCESS.md` §7 (assertive alone is
  unreliable across JAWS/Orca/TalkBack) — a screen-reader user lands directly on "Item not
  found. This record wasn't found. Nothing was changed." instead of silently at document top
- **Focus ring on the alert wrapper:** shown unconditionally on mount via a class toggle, not
  gated behind `:focus-visible` — programmatic focus must always be visible regardless of the
  browser's focus-visible heuristic for script-triggered focus. `2px solid accent-ink, 2px
  offset`, sitting outside the card's own border so it never merges with the card edge
- **"Back to items" button:** 44px height control floor (met at 44px exactly per §1 stack),
  `:focus-visible` ring `2px solid accent-ink, 2px offset`. Routes to the items list (surface
  03), the clear next action named in the copy
- **Reduced motion:** nothing to reduce — the error state resolves and renders immediately on
  route resolution, no skeleton stagger, no loading token to degrade
- **Content honesty:** the message states exactly what happened and what didn't ("Nothing was
  changed") — directly answers the live bug's actual failure mode, where a user could not tell
  whether their data had been wiped or never loaded

---

## 6. Content direction

One sentence, plain language, no jargon, no blame ("wasn't found" not "invalid request" or a
raw status code), paired with one unambiguous next action — this is the fix for a bug where
the previous silence was the entire problem.
