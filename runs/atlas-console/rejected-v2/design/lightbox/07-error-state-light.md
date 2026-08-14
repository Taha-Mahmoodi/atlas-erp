# lightbox: Surface 7 of 7 — Error State (Record Not Found)

**Mode:** light · **Canvas:** 1440×900 (fixed coded viewport, web/desktop-only) · **Composition
anchor:** `centered-statement` · **Background mode:** `flat-surface`

This comp fixes a **confirmed live-app defect**: navigating to a non-existent or malformed item
record ID today silently renders a blank "Edit item" form — every field empty, indistinguishable
from a form that just reset. The real 422 is visible only in devtools; nobody using the app can
tell what happened. The fix is structural, not decorative: one flat, plain, centered line of type
replaces the blank form, an assertive live-region announcement fires on render, and focus moves
directly to the message — so a screen-reader user hears the failure instead of landing on silence.

Job of this screen: state the failure in one honest sentence, confirm nothing was lost, and hand
back one real way out — nothing else earns a place on the plainest register in the set.

## Layout — numbers

Base unit: 8px. Control floor: 44px. Shell chrome (left rail + glass command bar) is identical to
surface 6's — this is a route inside the same authenticated shell, not a standalone page, so
navigation stays reachable while the content region reports the failure.

**Left rail** — `x:0–240, y:0–900`, flat, opaque, `substrate` fill, `1px solid hairline` right
edge (decorative only). Icon+label module nav, no blur, no glass. Nav list starts at `y:88`, each
item a 44px-tall row, 16px left padding, 20px icon + 8px gap + 14px/500 label. "Items" is the
active entry (`row-alt` fill behind that one row, text-primary weight, plus the 2px `accent-ink`
left-edge bar used elsewhere in this concept as the non-color active signal) — the invalid record
was reached from the Items module, so that's still the active section.

**Glass command bar** — the one glass object on the entire screen, per the concept's collision.
Fixed, floating: `top:16px, left:16px, right:16px` → `1408×56px`, `18px` border-radius. Fill
`color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)`, `backdrop-filter: blur(20px)
saturate(140%)`, border `color-mix(in oklab, white 70%, oklch(0.7 0.05 290) 30%)`. Same contents
as surface 6: brand glyph + wordmark, search field on its own text scrim, quick-create and
notifications icon-buttons, `44×44px` targets each.

**Glass never touches this error surface — how, not just stated:** content starts at `y:88`, a
full 16px clear gap below the bar's own `y:16–72` footprint. This screen never scrolls — the
message block is short, static, and centered inside a fixed-height region — so no pixel of the
error content ever passes underneath the bar's blur the way role-home's worklist deliberately
does. The rule holds structurally here, not just by omission.

**Content region** — `x:240–1440, y:88–900` (1200×812). No table, no chips, no card: the only
thing in this region is the centered message block below. Block centered on both axes *within
this content region* (not the full 1440-wide canvas), matching surface 6's own logic of keeping
replacement content aligned under the space it stands in for: horizontal center `x:840`
`((240+1440)/2)`, vertical center `y:494` `((88+900)/2)`.

**The message block** — no card, no shape, no icon, no color beyond the two text tokens below.
Total block height `88px` (28 + 16 + 44), so block spans `y:450–538`:

1. **`y:450–478` — the message, and the page's one `h1`:**
   `<h1 id="main-content" tabindex="-1" role="alert" aria-live="assertive" aria-atomic="true">`
   — "This record wasn't found. Nothing was changed." — 20px/600, `text-primary` weight but
   **error-hue color** `oklch(0.5 0.15 25)`. `display:inline-block; white-space:nowrap;` so it
   is guaranteed to render as one line regardless of font-metrics variance (the string is a fixed
   literal, not user content, so pinning it is safe) — renders at roughly 550–600px wide in Inter
   Variable SemiBold at 20px, comfortably inside the 1200px content region with wide margin either
   side. `role="alert"` already implies `aria-live="assertive" aria-atomic="true"`; both are
   stated explicitly here for build clarity, not because the implicit behavior is insufficient.
   On SPA route-entry (the router resolving an invalid ID), focus moves programmatically to this
   `h1` via script (`tabindex="-1"` makes it focusable) — the same pattern already used for the
   title `h1` on surfaces 04/05. Two independent signals, deliberately redundant: `role="alert"`
   fires an assertive announcement on insertion, and the explicit focus move guarantees the
   message is heard even in the screen-reader/browser combinations that don't reliably announce
   `alert` on a background SPA re-render. Because the `h1` is not an interactive control, its own
   `:focus` outline is suppressed (`outline: none`, scoped to this element only) — the focus move
   exists to get the message announced, not to draw a clickable-looking box around plain text; the
   visible focus ring below still applies to every real control on the page.

   **Why the message itself is the `h1`, not a separate heading with the message as body text**
   (a deliberate departure from surface 6, where `h1` stayed "Items" and the empty-line was a
   `<p>`): surface 6 is a list view whose identity persists through a zero-row filtered result, so
   "Items" is still the correct page title. This screen has no valid record left to title itself
   after — there is no honest short heading to put above the failure, so the failure *is* the
   page's title.

2. **`y:478–494` — 16px gap.**

3. **`y:494–538` — the recovery link:** "← Back to items" — plain flat text link, **not a
   button**, matching the exact component and copy already established for this module on
   surfaces 04/05. Body role, 14px/450, `accent-ink oklch(0.43 0.15 290)`. No underline at rest;
   underline on `:hover`/`:focus-visible` only. Real `<a href="/items">` — a genuine link, not a
   JS-only handler, so it survives a hard refresh and appears in a screen-reader link list.
   `aria-label="Back to items"` on the anchor (the leading "←" glyph is presentational only,
   matched to the same unmarked-arrow convention already used on surfaces 04/05, not re-litigated
   here). Sits inside a real 44px-tall click/tap zone, padding absorbing the difference from the
   14px visual line — the box itself is never painted.

   **Target-size decision, stated:** unlike "Clear filters" or "Log the first item" on surface 6
   — both genuinely inline within a running sentence, where the WCAG 2.5.8 inline exception
   applies directly — "Back to items" here sits on its own line below the message, not embedded
   in one. That is the same structural shape as the "← Back to Vendor Bills" / "← Back to items"
   links on surfaces 04/05, both of which take a real 44px block target. No inline exception
   applies; it gets the same real floor, per `ACCESS.md` row 1's "real margin, not a
   bare-minimum one."

**Skip link:** first in DOM/tab order, before the rail. Visually hidden (1×1px clipped) until
`:focus-visible`, then `top:16px; left:16px`, `accent-ink` background, white text, 14px/600,
`8px 16px` padding, `8px` radius, above everything including the glass bar — identical component
to surfaces 01/06. Copy: "Skip to error message" — targets `#main-content` (the `h1` above).

**Focus ring** (skip link, rail nav items, bar's search/quick-create/notifications controls,
"Back to items"): `2px solid accent-ink`, `2px` offset, `:focus-visible` only. The message `h1`
is explicitly excluded — see above.

**No card, no shape, no color-block, no icon anywhere in the content region.** The only
non-text asset on this screen is the shell chrome (rail, bar) shared with every other surface.

## Type

| Role | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| Wordmark (bar) | Inter Variable | 15px | 600 | 20px |
| h1 (title) — error message | Inter Variable | 20px | 600 | 28px |
| Body — "Back to items" link | Inter Variable | 14px | 450 | 20px |
| Command-bar label | Inter Variable | 14px | 500 | 20px |
| Rail nav label | Inter Variable | 14px | 500 | 20px |

`meta` (12px/450) is unused on this screen — no timestamps, no table headers, no data at that
register to show. No JetBrains Mono — no document identifier renders when there's no document.

## Color — paired, with ratios

| Use | Token | Value | Paired with | Ratio |
|---|---|---|---|---|
| Canvas, rail, content | substrate | `oklch(0.99 0.003 290)` | text-primary | ~16:1 |
| Rail active-row fill | row-alt | `oklch(0.965 0.006 290)` | text-primary | ~15:1 |
| Rail border | hairline | `oklch(0.90 0.008 290)` | — sub-3:1, decorative only |
| **Error message text** | error-text | `oklch(0.5 0.15 25)` | on substrate `oklch(0.99 0.003 290)` | **~6.3:1** — computed via OKLCH→sRGB conversion (Ottosson matrices); this pairing isn't tabulated in `DIRECTION.md` §7 (only the raw H25 value is given), so this is a worker-derived estimate, flagged for build-time re-verification per the concept's own §11 disclosure convention. Clears 4.5:1 with margin at 20px, well past the 3:1 large-text floor. |
| "Back to items" link, focus ring, skip-link bg | accent-ink | `oklch(0.43 0.15 290)` | on substrate | ~7.2:1 (per `DIRECTION.md` §7's own table, measured "on white" — substrate here is effectively the same lightness) |
| Glass command bar fill | glass panel | `color-mix(in oklab, oklch(0.98 0.01 290) 60%, transparent)` + `blur(20px) saturate(140%)` | text via inner scrim | flagged for build-time re-measurement (RISK 1), same as every other surface carrying this bar |

## Content direction

Terminology lock honored: "items" (lowercase, matching the module and the exact back-link copy
already used on surfaces 04/05), never "products" or "SKUs." The message is the concept's own
stated line, unmodified: "This record wasn't found. Nothing was changed." — no raw backend
string, no fabricated record ID, no invented brand claim, no lorem. "Back to items" is a real
route, not a placeholder href. Nothing on this screen implies data loss that didn't happen, and
nothing implies more happened than a failed lookup.

## Self-check (embarrassment gate)

Palette: error-text and accent-ink both traced against `DIRECTION.md` §7's light table or
computed directly where the table doesn't tabulate the pairing, and flagged rather than presented
as measured. Layout: four-band equivalent held (rail, bar, content, no bottom band needed on a
desktop-only surface); one `h1`; skip link; real 44px target on the only interactive text element
that isn't inline; `role="alert"` + programmatic focus both present, not one substituting for the
other. Glass touches nothing but its own 56px strip. No card, no icon, no fabricated data. Would
put my name on this.
