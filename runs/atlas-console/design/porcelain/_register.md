# porcelain — shared register spec (workers build against this file)

Gate A DECIDED 2026-08-14: porcelain, single direction, reference-conformance run
(PRINCIPLES §1–§3 suspended per TRANSLATE.md's recorded decision). Source register:
`../../gate-a-approved-porcelain.html` (`.po` / `.po.dark` blocks + the two comped frames)
and references 4 (Salung), 7 (Untitled UI), 9 (TrustToken), 2, 6 (glass layers) in
`../../references/`. Surfaces 02 and 03 MATCH the approved frames (refine, never redesign);
01, 04, 05, 06, 07 extend the same register. No metaphors, no invented concepts, no new hues.

## 1. Palette — VERIFIED (script-computed WCAG ratios, 2026-08-14; do not re-derive)

One adjustment was made to the approved starting values and is final:
**warn-tx light `#96660f` → `#94650c`** (pill pair was 4.46, below the 4.5 floor; one 0.005
OKLCH L step, hue/chroma held; now 4.54). Everything else passes as approved.

### Light

| Token | Hex | OKLCH | Paired foreground → ratio |
|---|---|---|---|
| bg | `#f7f7f8` | `oklch(97.6% 0.001 286.4)` | ink → **16.57** · ink2 → **4.81** · acc → **4.86** |
| card | `#ffffff` | `oklch(100% 0 0)` | ink → **17.74** · ink2 → **5.15** · acc → **5.20** · ok-tx → **5.37** · bad-tx → **6.16** · warn-tx′ → **5.09** |
| ink (text-primary, btn fill) | `#17181c` | `oklch(21.0% 0.008 274.5)` | white on it → **17.74** (ink button) |
| ink2 (text-secondary) | `#6b6d76` | `oklch(53.6% 0.014 275.9)` | (as fg, see bg/card rows) |
| line (hairline) | `#e9e9ee` | `oklch(93.5% 0.007 286.3)` | decorative only — 1.21 vs card, 1.13 vs bg; NEVER the sole boundary/state signal |
| acc | `#3f5bf6` | `oklch(55.0% 0.232 269.1)` | on acc-t → **4.58**; as focus ring vs bg → **4.86** (floor 3.0); sparkline vs card → **5.20** (floor 3.0) |
| acc-t | `#edf0fe` | `oklch(95.7% 0.019 276.3)` | acc on it → **4.58** |
| ok-bg | `#e7f6ed` | `oklch(96.0% 0.020 159.8)` | ok-tx on it → **4.80** |
| ok-tx | `#177a48` | `oklch(51.3% 0.118 155.2)` | — |
| warn-bg | `#fbf1de` | `oklch(96.1% 0.027 83.5)` | warn-tx′ on it → **4.54** |
| **warn-tx′ (FINAL)** | `#94650c` | `oklch(54.3% 0.110 75.8)` | — |
| bad-bg | `#fbe9e7` | `oklch(94.8% 0.020 25.2)` | bad-tx on it → **5.25** |
| bad-tx | `#b23425` | `oklch(51.3% 0.165 30.3)` | — |
| shadow | `0 1px 2px rgba(23,24,28,.04), 0 10px 28px -8px rgba(23,24,28,.09)` | — | — |
| glass composite (palette bg, worst underlay) | 62% card over bg = `#fcfcfc` | — | ink on it → **17.29** *(computed, not rendered)* |

### Dark

| Token | Hex | OKLCH | Paired foreground → ratio |
|---|---|---|---|
| bg | `#131418` | `oklch(19.2% 0.008 274.5)` | ink → **15.91** · ink2 → **6.74** · acc → **7.95** |
| card | `#1b1c22` | `oklch(22.8% 0.012 278.0)` | ink → **14.68** · ink2 → **6.23** · acc → **7.34** · ok-tx → **9.76** · warn-tx → **8.98** · bad-tx → **7.37** |
| ink | `#eeeef2` | `oklch(95.0% 0.005 286.3)` | ink-btn dark = ink fill, `#17181c` text on it → **15.33** |
| ink2 | `#9a9ca8` | `oklch(69.5% 0.018 278.4)` | — |
| line | `#2a2c35` | `oklch(29.5% 0.017 275.5)` | decorative only — 1.22 vs card |
| acc | `#93a5ff` | `oklch(74.5% 0.132 274.2)` | on acc-t → **6.46**; focus ring vs bg → **7.95**; sparkline vs card → **7.34** |
| acc-t | `#232637` | `oklch(27.4% 0.032 276.4)` | — |
| ok-bg / ok-tx | `#1b2f24` / `#7fd6a4` | `oklch(28.4% 0.033 159.3)` / `oklch(80.7% 0.111 157.5)` | pill → **8.15** |
| warn-bg / warn-tx | `#332a17` / `#e4b566` | `oklch(29.0% 0.034 85.0)` / `oklch(79.9% 0.111 79.1)` | pill → **7.48** |
| bad-bg / bad-tx | `#361f1c` / `#eb9486` | `oklch(26.8% 0.037 27.8)` / `oklch(75.2% 0.108 29.7)` | pill → **6.65** |
| shadow | `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)` | — | — |
| glass composite | 62% card over bg = `#18191e` | — | ink on it → **15.17** *(computed, not rendered)* |

Dropped from the approved HTML: `--ink3:#9becb0` (dead variable, referenced nowhere; a mint
green mislabeled as a neutral). Disabled text: ink2 at 55% opacity, contrast-exempt (WCAG
disabled exemption), never the only disabled signal — disabled controls also lose border
emphasis and pointer affordance.

## 2. Type system

| Role | Face | Spec | Used for |
|---|---|---|---|
| h1 / page title | Inter Variable | 22px/650, −0.01em, lh 28 | one per screen, the page title |
| stat value | Inter Variable | 26px/650, tnum, lh 32 | stat-card numbers |
| body / table | Inter Variable | 13px/450, lh 20 | table cells, general copy |
| nav | Inter Variable | 13.5px/500 (550 active) | sidebar rows, palette rows |
| sub / meta | Inter Variable | 12–13px/450, ink2 | crumbs, subtitles, pagination |
| delta / fine | Inter Variable | 11.5px/450 | stat deltas, table sub-lines |
| pill | Inter Variable | 12px/500 | status pills |
| mono-caps label | **JetBrains Mono Variable** | 10.5px/600, .06–.07em, uppercase | section labels, stat labels, th |
| identifier | **JetBrains Mono Variable** | 11px/500 | ITM-…, BILL-…, PO-… codes |
| kbd chip | **JetBrains Mono Variable** | 11px/450 | keycap chips |

Both faces self-hosted (Inter Variable already load-bearing in repo; JetBrains Mono Variable
added, subset to Latin + tabular digits). Fallback stacks: Inter → system-ui;
JetBrains Mono → ui-monospace, 'SF Mono', Menlo, Consolas. Numbers in data contexts always
`font-variant-numeric: tabular-nums` (Inter's tnum for table figures; mono reserved for
identifiers and caps labels).

## 3. Component inventory (exact values from the approved frames)

- **Sidebar**: 248×900, card fill, 1px line right border, padding 16px 12px, flex column.
- **Workspace switcher**: 1px line border, r10, pad 8px 10px, 26px mark (r7, ink fill,
  white 12px/700 "A"), name 13px/600 + sub 11px ink2, chevron right.
- **Section label**: mono-caps spec (§2), ink2, pad 0 10px, margin 14px 0 6px.
- **Nav row**: h 38px, r9, pad 0 10px, gap 10px, 13.5px ink2, 15px icon (1.7px stroke);
  active: acc-t fill, acc text, weight 550; count badge 11px ink2 right-aligned.
- **User card**: pinned bottom (margin-top auto), 1px line border, r12, pad 10px, 30px
  avatar (acc-t fill, acc initials 11px/650), name 12.5px/600, sub 11px ink2.
- **Main region**: x 248, w 1192, pad 28px 36px → 1120px usable content width.
- **Breadcrumb**: 12px ink2, current segment ink /500, 10px below top.
- **Page head**: h1 (§2) + sub 13px ink2 left; controls right, 10px gap.
- **chip button** (secondary): h 38px visual, pad 0 14px, 1px line border, r10, card fill,
  13px ink. **ink button** (primary): h 38px visual, pad 0 16px, ink fill, r10,
  13px/550 white (dark: ink fill = #eeeef2, text #17181c).
  **44px policy**: both keep 38px visual in the page head with hit-target extended to 44px
  (transparent hit-area inset, recorded); standalone primaries NOT in the approved frames
  (login submit, form save, empty/error CTAs) render 44px tall outright, r10.
- **Stat card**: r14, 1px line border, shadow, pad 16px 18px; mono-caps label + optional
  sparkline 76×22 (acc stroke 1.8px, fill none) on the label row; value 26px/650 tnum;
  delta 11.5px ink2 with ok-tx ↑ / bad-tx ↓ spans.
- **Panel**: card fill, r14, 1px line border, shadow, pad 18px; panel head = mono-caps
  label left + 12px meta/link (acc) right, margin-bottom 14px.
- **Table**: th mono-caps 10.5px ink2, pad 8px 10px, 1px line bottom border; td 13px,
  pad 11px 10px, 1px line bottom border (last row none); numeric cells right-aligned tnum;
  identifier sub-line 11px mono ink2.
- **Status pill**: inline-flex, h 24px, r-full, pad 0 10px, 12px/500, 7px currentColor dot,
  5px gap. Variants: ok (In stock / Posted / Paid) · warn (Low stock / Pending) · bad
  (Out of stock / Mismatch / Overdue) · mute = Draft (transparent fill, 1px dashed line
  border, ink2 text, no dot). Dot + label always — never color alone.
- **Filter chip**: h 30px, r-full, acc-t fill, acc text 12.5px, ✕ dismiss (accessible name
  "Remove filter: …"). "+ Add filter" ghost text button, 13px acc.
- **Search field**: h 38px, w 260px, 1px line border, r10, card fill, 13px ink2 placeholder,
  15px search icon, trailing ⌘K kbd chip.
- **⌘K glass palette** (floating layer ONLY): w 330px, r16, pad 10px, bg = 62% card +
  `backdrop-filter: blur(18px) saturate(150%)`, border 1px `color-mix(in srgb, card 40%,
  #ffffff88)` (dark: 14% white), shadow `0 24px 60px -12px rgba(23,24,28,.28)`; row h 44px,
  r10, 13.5px ink, 15px icon; highlighted row 85% card + `0 2px 8px rgba(23,24,28,.08)`;
  kbd chips 22px min, r6, 1px line border, card fill, `0 1px 0 line`.
  Semantics: `role="dialog"` + combobox/listbox pattern, focus-trapped, Esc closes,
  focus returns to invoker. **Reduced motion: blur-in degrades to instant, fully opaque
  card panel — a designed state, not a fallback.** Nothing structural ever blurs.
- **Bar chart** (role home): paired bars, gray = line token, ink = ink token, r 5/5/2/2,
  180px tall, axis labels 10.5px ink2. Monochrome — the accent is not a data color.
- **Skeleton**: line-token blocks (dark: line token) matching final layout geometry exactly,
  r6; shimmer only when motion is allowed; never a spinner for layout-shaped loads.
- **Focus ring**: 2px solid acc, 2px offset, `:focus-visible` only — verified vs bg (4.86 /
  7.95), card, acc-t, and the glass palette (scrim guarantees composite).
- **Pagination**: 12.5px ink2, "Showing X–Y of N" left, Prev · pages · Next right.

## 4. Layout constants @ 1440×900

Sidebar 248. Main 1192, pad 28/36 → content 1120. Stats: 4-col, gap 16 → 268px each.
Two-col panels: 1.2fr/1fr, gap 16 → 602/502. Base spacing unit 8px (4px half-steps as in
the approved frames). Radii: 9 (nav) / 10 (controls) / 12 (user card) / 14 (cards/panels) /
16 (glass palette) / 999 (pills).

## 5. Accessibility constants (every comp cites what applies)

- Skip link first in tab order, visible on focus, targets `#main-content`. One `h1`, one
  `main`, one `nav aria-label="Primary"` per screen.
- Work lists: `role="grid"`, roving tabindex, arrows/Home/End/Ctrl+Home, Enter opens or
  enters widget-editing, Esc restores grid nav, Space selects, Shift+arrows extend.
- Icon-only controls: per-record accessible names ("Open ITM-BOLT-M6X20", never "Edit").
- Row-action clusters: WCAG 2.5.8 spacing exception, ≥24px centre-to-centre; everything
  else ≥44px target (§3 policy). Density toggle exists; compact rows ≥36px, controls ≥40px.
- SPA route change → focus to h1 (`tabindex="-1"`). Deleted row → next row / table if empty.
- Live regions: polite for saved/count changes; assertive + focus-move for session-expiry,
  failed save, conflict.
- Auth: paste and password managers never blocked; no cognitive-test CAPTCHA (3.3.8).
- Reduced motion: palette blur-in → instant opaque; skeleton shimmer → static; no parallax
  anywhere in this register.
- Terminology lock: item / vendor / customer / warehouse / journal entry. No invented brand
  marks, no invented persons beyond the seed-data register (Amira K., Buyer · Procurement).

## 6. Comp file format (match rejected-v2 resolution — this is the benchmark)

Each `-light.md`: (1) header naming surface, mode, canvas 1440×900, composition anchor +
background mode from the closed menus; (2) region map table with x,y,w,h sums checked;
(3) per-region spec citing exact tokens/type roles; (4) content — real fields, real
plausible data, no lorem; (5) the data states this surface owes, each designed;
(6) type-table citation (deltas from §2 only); (7) palette citation — ONLY pairs used, with
the §1 verified ratios (never re-derive, never estimate); (8) accessibility notes for this
surface; (9) a self-check line (sums re-added, tokens read back against this file).
Each `-dark.md`: full header + dark palette pairs with §1 ratios + everything that differs
(shadows, glass, sparkline, focus, any material notes); layout math may reference the
light file instead of duplicating it.

Closed menus for the log — anchor: centered-statement · dense-grid · stacked-center ·
left-rail-caption · right-rail-caption · split-pane. Background: flat-surface ·
soft-gradient · glass-layer · image. (The floating palette does not change a surface's
background mode.)
