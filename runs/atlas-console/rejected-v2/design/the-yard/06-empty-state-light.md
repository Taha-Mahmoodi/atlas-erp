# the yard: Surface 6 of 7 — Empty State (Filtered)

Mode: **light**. Canvas: fixed **1440×900** coded viewport (web/desktop-only, no platform mode).
Screen: Items list, filtered to zero results (`category = NON_STOCKED`, no matches).
Composition anchor: **centered-statement**. Background mode: **flat-surface**.

Job of this screen: tell the operator unambiguously that their *filters*, not the system,
produced zero rows — and give them a one-click way back — without ever looking like the
true first-run empty state. This is the fix for the confirmed defect where both currently
render identically.

---

## 1. Layout — region map (8px base unit throughout)

| Region | Bounds (x, y, w, h) | Notes |
|---|---|---|
| Left rail | 0, 0, 232, 900 | full height, `card` fill, 1px `hairline` right border |
| Title band | 232, 0, 1208, 64 | sticky, `card` fill |
| Filter-chips band | 232, 64, 1208, 56 | sticky (`space-sticky = 56px`), `card` fill, 1px `hairline` bottom border — **present in this state, absent in true-empty (see §5)** |
| Empty-state region | 232, 120, 1208, 780 | `substrate` fill, content centered |

Skip link: visually hidden, first in tab order, reveals on `:focus` at `(16, 16)` over the
title band; targets `#main-content`. One `<main id="main-content">` wraps the title band
through the empty-state region. One `<nav aria-label="Primary">` wraps the left rail.

### Left rail (232px)
- `0,0,232,64` — wordmark "Atlas" (real product name, no logo mark, per no-brand rule), 14px/600, `text-primary`, padding-left 24px, vertically centered.
- Nav items below, 44px height each, full rail width minus 16px horizontal margin, 12px internal padding, 20px icon + 14px/450 label, 8px gap between icon and label: Home · **Inventory (active)** · Procurement · Sales · Finance · Reporting · Admin · — spacer — · Help (pinned last, fixed relative position, per the run's system rule).
- Active state (Inventory): rail-item background `accent-tint`, text `accent-ink`, 3px `accent-ink` left indicator bar flush to the rail's left edge.

### Title band
- h1 "Items" — 20px/600, `text-primary`, left-aligned, padding-left 32px, vertically centered in the 64px band. **Screen identity unchanged by the filter state.**
- Secondary "+ New item" button, right-aligned, 32px from the right edge, 44px height, 16px horizontal padding, `card` fill, 1px `hairline` border, radius 12px, 14px/500 `accent-ink` label. Kept secondary-emphasis so it never competes with this screen's real subject: getting back to a non-empty list.

### Filter-chips band (56px, present only when filters are active)
- Padding-left 32px, vertically centered row.
- Meta label "Filters" — 12px/450 `text-secondary`.
- 12px gap, then one chip: rounded-full pill, 44px height (clears the control floor directly — no icon-cluster exception needed), 16px horizontal padding, `accent-tint` fill, `accent-ink` text 14px/450: **"Category: Non-stocked"**, trailing 16px × glyph (`accent-ink`), 8px gap before it. `aria-label="Remove filter: Category — Non-stocked"` on the chip's dismiss control. `:focus-visible` ring: 2px solid `accent-ink`, 2px offset.
- This row is *why* the operator understands they're seeing nothing — it stays visible and each chip is independently removable.

### Empty-state region (780px, centered-statement)
Content block is a single 480px-wide column, horizontally centered in the 1208px content
area, vertically centered in the 780px band (block height ≈360px, so top ≈ y 330).

1. **Dashed-outline token slot** — 96×96px, radius 24px (bento's rounded-corner language,
   matching every signal-token in the system), border 2px **dashed**, color `hairline`
   `oklch(0.89 0.01 290)`, fill transparent (substrate shows through — the slot reads as an
   empty groove, not a card). Centered inside: a static 28px outline glyph, 2px stroke,
   `text-secondary` — a magnifier with a diagonal slash ("no result"), **not** the pencil/
   dashed-ring glyph the concept reserves for the Draft signal-token, and **not**
   interactive. Nothing lives inside this slot in the filtered state — see §5 for why the
   true-empty slot holds a real button instead.
2. Gap 24px.
3. h2 "No items match these filters." — 20px/600, `text-primary`, centered.
4. Gap 8px.
5. Body line — 14px/450, `text-secondary`, centered, max-width 400px: "Try removing a
   filter or broadening your search."
6. Gap 24px.
7. **"Clear filters" button** — 44px height (control floor), min-width 180px, 20px
   horizontal padding, radius 12px, fill `accent-ink`, label "Clear filters" 14px/600
   white — this exact fill/foreground pairing is the palette table's verified ~7:1 (`accent-ink`
   ↔ white), not the borderline `accent-emphasis` (~4.8:1) pairing, which this screen
   deliberately avoids. `aria-label="Clear filters — removes Category: Non-stocked"` so the
   accessible name states which filters it clears even though the visible label stays short.
   `:focus-visible` ring: 2px solid `accent-ink`, 2px offset, checked against both the
   `substrate` background and the button's own `accent-ink` fill (ring sits outside the fill
   so it never merges with it, same rule as the ring-vs-token-fill check elsewhere in this
   concept).
8. Gap 8px, meta caption below the button — 12px/450, `text-secondary`, centered:
   "Removes: Category = Non-stocked" — the visible, plain-language restatement of exactly
   what one click undoes.

Live region (visually hidden, `role="status"`, `aria-live="polite"`): **"0 items match your
filters."** — announces once, on the filter-to-zero transition; polite per the access
decision, since this is a state description, not an alert.

---

## 2. Type table

| Level | Face | Size/weight | Line-height | Used for |
|---|---|---|---|---|
| Title | Inter Variable | 20px/600 | 28px (1.4) | h1 "Items"; h2 "No items match these filters." |
| Body/data | Inter Variable | 14px/450 | 20px (1.43) | rail labels, chip label, body line, secondary button label, "Clear filters" label |
| Meta | Inter Variable | 12px/450 | 16px (1.33) | rail wordmark's sibling meta, "Filters" label, "Removes: …" caption |

No metric-display, lane-header, or mono-identifier sizes appear on this screen — none of
this screen's content is a metric, a lane header, or a document identifier.

---

## 3. Palette — paired, with measured ratios (from `DIRECTION.md` §6)

| Token | Value | Used for | Paired fg | Est. ratio |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.004 290)` | empty-state region fill | text-primary | ~15:1 |
| card | `oklch(1 0 0)` | rail, title band, chips band | text-primary | ~16:1 |
| text-primary | `oklch(0.21 0.015 290)` | h1, h2, wordmark | — | — |
| text-secondary | `oklch(0.46 0.02 290)` | body line, meta caption, glyph, "Filters" label | on card/substrate | ~6.5:1 |
| hairline | `oklch(0.89 0.01 290)` | rail border, chips-band border, dashed slot outline, "+ New item" border | decorative-only, sub-3:1, never the sole boundary signal | — |
| accent-ink | `oklch(0.44 0.15 290)` | active-rail text/indicator, chip text, "+ New item" label, "Clear filters" fill, focus ring | white / on card | ~7:1 |
| accent-tint | `oklch(0.94 0.035 290)` | active-rail background, chip fill | accent-ink | ~6:1 |
| accent-emphasis | `oklch(0.53 0.18 290)` | **not used on this screen** — reserved for large/graphical CTA placements elsewhere in the run; its ~4.8:1 white pairing is flagged borderline (RISK 4) and this screen's one button stays on the verified `accent-ink` pairing instead | white | ~4.8:1 (unverified) |

---

## 4. Content direction (one line)

Every string is a realistic list-filter interaction, not populated placeholder copy: one
real filter ("Category: Non-stocked"), one plain-language explanation, one action whose
label and accessible name both say exactly what it undoes — no invented data, no lorem, no
superlative.

---

## 5. True-empty comparison (documentation only, not this comp's render)

The unfiltered, brand-new-tenant empty state — for contrast, so the difference the brief
is asking for is written down rather than implied:

- **Chips band is absent entirely** (no filters exist to show), reclaiming its 56px — the
  empty-state region runs the full `232,64,1208,836`.
- h1 stays **"Items"** — identical to the filtered state; screen identity never changes.
- h2 reads **"No items yet — log the first one."**
- The dashed 96×96 slot is not decorative in this variant — it **contains the primary
  action itself**: a 44px-min-height "+ Log item" button sized to the slot, radius 12,
  fill `accent-ink`, 14px/600 white label (kept on the same verified `accent-ink` pairing
  as the filtered state's "Clear filters," rather than reaching for `accent-emphasis`; the
  access note permits `accent-emphasis` here *if* the label is set ≥16px/600, which this
  screen's fixed three-size scale doesn't offer without a one-off — `accent-ink` sidesteps
  that question entirely and keeps both empty variants on one verified pairing).
- Below the slot, a teaching line replaces the filtered state's "Try removing a filter…":
  14px/450 `text-secondary`, **"Items you log here appear in this list, ready for
  procurement and stock counts."** — because this is plausibly a brand-new tenant's first
  screen, so it has to say what the screen is for, not just that it's empty.
- No "Clear filters" action and no meta caption exist in this variant — there is nothing
  to clear.

**The mechanism that keeps the two states visibly distinct, stated once:** the dashed slot
is *content* in true-empty (a button lives inside it — an invitation to fill the groove)
and *decoration* in filtered-empty (a static, non-interactive glyph — the groove is empty
because of a choice the operator made, not because nothing exists yet). Everything else —
copy register, presence of the chips band, presence of a "Clear filters" action — follows
from that one structural difference.
