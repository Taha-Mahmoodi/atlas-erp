# porcelain · 02 Role home — light · 1440×900

Composition anchor: **left-rail-caption** · Background mode: **flat-surface**
(⌘K glass palette is a floating layer per _register.md §6 — it does not change the background mode.)
Reference-conformance surface: MATCHES the approved frame (`gate-a-approved-porcelain.html` 294–360). Refinements only, flagged inline.

## 1. Region map @ 1440×900

| Region | x | y | w | h | Check |
|---|---|---|---|---|---|
| Sidebar | 0 | 0 | 248 | 900 | 248+1192=1440 ✓ |
| Main | 248 | 0 | 1192 | 900 | pad 28/36 → content 1120 (1192−72) ✓ |
| Breadcrumb | 284 | 28 | 1120 | 16 | 12px lh 16 |
| Page head | 284 | 54 | 1120 | 49 | crumb 44 + 10 mb → 54 ✓ |
| Stat row | 284 | 127 | 1120 | 116 | 54+49+24 mb = 127 ✓ · 4×268 + 3×16 = 1120 ✓ |
| Cash flow panel | 284 | 263 | 602 | 299 | 127+116+20 mb = 263 ✓ |
| Needs-action panel | 902 | 263 | 502 | 299 | 284+602+16 = 902 ✓ · 602+502+16 = 1120 ✓ |
| Quiet field below panels | 284 | 562 | 1120 | 310 | held bg, no filler — 562+310 = 872 = 900−28 ✓ |
| ⌘K palette (floating) | 1038 | 250 | 330 | 198 | 1440−72−330 = 1038 ✓ (right 72, top 250) |

Panel heights: cash flow inner 16 (phead) + 14 + 180 (bars) + 8 + 14 (axis) = 232 + 36 pad + 2 border = 270; action panel inner 30 + 231 (rows 58+58+58+57) = 261 + 36 + 2 = 299. Grid stretch equalizes both to **299**.
Palette height: 4×44 rows + 20 pad + 2 border = 198.

## 2. Per-region spec

### Sidebar (248×900, card `#ffffff`, 1px line right border, pad 16px 12px, flex column)
- **Workspace switcher**: 1px line border, r10, pad 8px 10px; 26px mark r7 ink fill, white 12px/700 "A"; "Atlas" 13px/600, "Acme Co." 11px ink2; chevron right (ink2, 15px/1.7px). mb 20.
- **Section label** "MAIN MENU": mono-caps §2 (JetBrains Mono 10.5px/600 .06em uppercase), ink2, pad 0 10px, margin 14 0 6.
- **Nav rows** h38, r9, pad 0 10px, gap 10, 13.5px/500 ink2, 15px icons 1.7px stroke:
  Dashboard **(active: acc-t fill `#edf0fe`, acc `#3f5bf6` text, 550)** · Items ·214· · Purchase orders ·18· · Sales orders ·27· · Finance · HR. Count badges 11px ink2, right-aligned.
- **Section label** "INSIGHTS", then Reports · Settings (same row spec).
- **User card** pinned bottom (margin-top auto; y≈832): 1px line border, r12, pad 10; 30px avatar acc-t fill / acc "AK" 11px/650; "Amira K." 12.5px/600; "Buyer · Procurement" 11px ink2.

### Breadcrumb + page head
- Crumb: "Dashboard / **Overview**" — 12px ink2, current segment ink/500. mb 10.
- h1 **"Welcome back, Amira"** 22px/650 −0.01em lh 28; sub "Thursday 14 August · Acme Co." 13px ink2, 3px below.
- Right controls, gap 10: **chip button** "This month ▾" (h38 visual, pad 0 14, 1px line border, r10, card fill, 13px ink) · **ink button** "Export CSV" with file icon (h38 visual, pad 0 16, ink `#17181c` fill, r10, 13px/550 white). Both extend hit-target to 44px via transparent inset (§3 policy, recorded).

### Stat row (4× 268×116, gap 16)
Card: r14, 1px line border, shadow token, pad 16px 18px. Label row = mono-caps 10.5px/600 .07em ink2 left + **sparkline 76×22 right (acc `#3f5bf6` stroke 1.8px, fill none — vs card 5.20, §1; graphical floor 3.0 ✓)**. Value 26px/650 tnum lh 32, mt 8. Delta 11.5px/450 ink2, mt 6; ↑ spans ok-tx, ↓ spans bad-tx.

| # | Label | Sparkline | Value | Delta |
|---|---|---|---|---|
| 1 | TOTAL REVENUE | yes — points (0,18 12,15 24,17 36,10 48,12 60,6 72,9 80,4) in 80×24 viewBox | $128,400 | **↑ 2.6%** (ok-tx) vs last month |
| 2 | OPEN ORDERS | yes — points (0,12 12,14 24,9 36,13 48,8 60,11 72,7 80,10) | 132 | **↑ 8** (ok-tx) vs last week |
| 3 | LOW-STOCK ITEMS | none | 6 *of 214* (small: 12px/450 ink2, baseline-aligned) | **↑ 2** (bad-tx — rising is bad here) need reorder |
| 4 | AP DUE THIS WEEK | none | $23,900 | 4 vendor bills (plain ink2, no arrow) |

Money: `$` + comma-grouped integer, `font-variant-numeric: tabular-nums` (Inter tnum, §2) — everywhere money renders on this surface.

### Cash flow panel (602×299)
- Panel: card, r14, 1px line border, shadow, pad 18. Phead: "CASH FLOW" mono-caps ink2 left; right meta 12px ink2 "Weekly · Monthly · **Yearly**" (active segment ink/500). mb 14.
- **Paired-bar chart, monochrome — gray = line `#e9e9ee`, ink = ink `#17181c`. The accent is never a data color.** Bars flex 1:1 in 6 groups, group gap 14, intra-pair gap 4, r 5/5/2/2, field h 180.
- Heights (% of 180 → px): Mar 42/60 (76/108) · Apr 35/48 (63/86) · May 55/73 (99/131) · Jun 48/52 (86/94) · Jul 62/88 (112/158) · Aug 50/70 (90/126).
- Axis: Mar Apr May Jun Jul Aug — 10.5px ink2, centered per group, pad-top 8.
- Note: gray bar (line token) is 1.21 vs card — legal because it is a filled shape read by area against ink pairs, and the chart carries `role="img"` text alternative (§8 below); line remains banned as a *sole* boundary/state signal per §1.

### Needs your action panel (502×299)
- Phead: "NEEDS YOUR ACTION" mono-caps ink2 left; "View all" 12px acc link right. mb 14.
- Table, no thead in this comp; td 13px pad 11px 10px, 1px line bottom border, last row none. Col 1: identifier bold 13px + sub-line 11.5px ink2 vendor name. Col 2: right-aligned tnum money. Col 3: w 96, status pill (h24, r-full, pad 0 10, 12px/500, 7px currentColor dot + 5px gap; mute = dashed line border, ink2, no dot).

| Identifier | Vendor | Amount | Pill |
|---|---|---|---|
| PO-2026-00842 | Meridian Supply Co. | $4,280 | warn · dot · "Pending" (warn-bg/warn-tx′) |
| BILL-2026-01187 | Cascade Fasteners | $1,096 | bad · dot · "Mismatch" (bad-bg/bad-tx) |
| PO-2026-00845 | Norbright Industrial | $780 | mute · "Draft" (dashed line border, ink2) |
| BILL-2026-01190 | Solara Components | $12,450 | ok · dot · "Posted" (ok-bg/ok-tx) |

### ⌘K glass palette (floating layer, 330×198 @ 1038,250 — comped OPEN; closed is the default state, §5c)
- Material: r16, pad 10, bg = 62% card + `backdrop-filter: blur(18px) saturate(150%)`; border 1px `color-mix(in srgb, card 40%, #ffffff88)`; shadow `0 24px 60px -12px rgba(23,24,28,.28)`. Worst-underlay composite `#fcfcfc`, ink on it **17.29** (§1, computed).
- Rows h44, r10, gap 12, pad 0 12, 13.5px ink, 15px icon; **highlighted row = 85% card + `0 2px 8px rgba(23,24,28,.08)`**. Kbd chips: JetBrains Mono 11px/450, min-w 22, h22, r6, 1px line border, card fill, `0 1px 0 line`, ink2.

| Row | Icon | Kbd | State |
|---|---|---|---|
| New item | plus | ⌘ N | — |
| Receive stock | box | ⌘ R | **highlighted** |
| Pay vendor bill | dollar | ⌘ B | — |
| Jump to record… | search | ⌘ K | — |

- **Semantics (full, per register §3)**: `role="dialog"` `aria-modal="true"` `aria-label="Command palette"`. Combobox+listbox pattern: query input `role="combobox"` `aria-expanded="true"` `aria-controls` → the listbox; four rows `role="option"` in `role="listbox"`; highlight tracked via `aria-activedescendant` (→ "Receive stock"). Focus trapped inside the dialog; ↑/↓ move activedescendant; Enter runs; **Esc closes and returns focus to the invoker** (the element focused at ⌘K time). Page behind is `inert`.
- **Refinement, flagged**: the approved frame draws only the four option rows; the combobox pattern the register itself mandates requires a query input — built component adds it as row 0 (same 44px row geometry, no fill, 13.5px ink, ink2 placeholder "Type a command…"), which grows the open palette to 242px tall. Comp geometry above records the frame as approved.
- **Reduced motion: blur-in degrades to an instant, fully opaque card panel — a designed state, not a fallback** (card fill, same border/shadow/rows). Nothing structural ever blurs.

## 3. Data states owed

**(a) Loading** — skeletons match final geometry exactly; line-token `#e9e9ee` blocks, r6; **shimmer only when motion allowed, static otherwise; never a spinner** (§3):
- Page head: 220×22 block (h1) + 160×13 (sub); controls render live (they don't load).
- Each stat card (same 268×116 shell, real border/shadow): 96×10 label block, 128×26 value block mt 8, 88×11 delta block mt 6. Card 1–2 also 76×22 spark block on the label row.
- Cash flow panel (same shell): 72×10 phead block + 180-tall field of 6 paired r6 bar blocks at the final heights, all line token; axis = 6× 28×10 blocks.
- Action panel (same shell): 128×10 phead block + 4 rows each 132×13 + 96×11 (col 1), 56×13 right (col 2), 72×24 r-full (col 3), row borders live.

**(b) "Needs your action" empty** — panel and phead stay exactly as specced; table replaced by one line: **"Nothing needs you right now."** — 13px/450 ink2, top-aligned where row 1 sat (y +14 under phead). No illustration, no icon, no CTA. "View all" link remains.

**(c) Palette closed (default)** — surface ships with the palette absent; no scrim, no reserved space (it is a floating layer). Invoked by ⌘K from anywhere in the shell. The comp shows it open to demonstrate the glass moment.

## 4. Type citation (deltas from §2: none)
h1 22px/650 · stat value 26px/650 tnum · body/table 13px/450 · nav+palette rows 13.5px/500 (550 active) · sub/meta 12–13px/450 ink2 · delta 11.5px/450 · pill 12px/500 · mono-caps 10.5px/600 .06–.07em · identifier 11px mono/500 (sub-lines here render 11.5px per the approved frame — recorded as-approved) · kbd 11px mono/450.

## 5. Palette citation (§1 verified — pairs used only, never re-derived)
- ink on bg **16.57** · ink on card **17.74** · ink2 on bg **4.81** · ink2 on card **5.15**
- acc on card (sparkline, "View all", icons) **5.20** · acc on acc-t (active nav) **4.58** · acc focus ring vs bg **4.86** (floor 3.0)
- white on ink (ink button) **17.74**
- pills: ok-tx/ok-bg **4.80** · warn-tx′ `#94650c`/warn-bg **4.54** · bad-tx/bad-bg **5.25**
- ok-tx on card (↑ deltas) **5.37** · bad-tx on card (↓ delta) **6.16**
- glass composite worst underlay: ink on `#fcfcfc` **17.29**
- line: decorative only (1.21 vs card) — every boundary it draws is doubled by fill/shadow/spacing; every state by dot+label.

## 6. Accessibility (this surface)
- Skip link first in tab order → `#main-content`; one `h1` ("Welcome back, Amira" — semantic h1 even though the frame markup used h2), one `main`, `nav aria-label="Primary"`.
- SPA route entry → focus h1 (`tabindex="-1"`).
- Sparklines `aria-hidden="true"` — the stat value/delta text is the data. Bar chart: `role="img"`, `aria-label="Cash flow, March to August, inflow vs outflow per month; detail in Reports"`.
- Pills: dot + label always, never color alone; Draft mute variant signaled by dashed border + text, not color.
- Action rows: full-row link, accessible name per record ("Open PO-2026-00842, Meridian Supply Co., $4,280, Pending").
- Palette semantics as §2 above; live region `polite` announces result count on filter; skeleton region `aria-busy="true"`.
- Focus ring 2px acc, 2px offset, `:focus-visible` only — 4.86 vs bg, verified vs card/acc-t/glass (§1).
- Terminology lock honored: item / vendor / customer / warehouse; persons limited to Amira K. (seed register).

## 7. Self-check
248+1192=1440 ✓ · 1192−(36×2)=1120 ✓ · 4×268+3×16=1120 ✓ · 602+502+16=1120 ✓ · 28+16+10+49+24+116+20+299=562, +310 quiet field+28 pad=900 ✓ · palette 1038+330+72=1440 ✓ · all hexes and ratios read back against _register.md §1 (warn-tx′ `#94650c` @ 4.54 — the FINAL adjusted value, not the frame's `#96660f`; `--ink3` dead variable not carried) ✓ · tokens logged from §6 closed menus ✓.
