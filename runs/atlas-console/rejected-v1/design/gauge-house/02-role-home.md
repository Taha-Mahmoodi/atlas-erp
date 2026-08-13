gauge-house: Surface 2 of 7 — Role home

Canvas: 1440×900 fixed desktop viewport. Sticky header reserved 48px.

## Composition anchor: `dense-grid`
## Background mode: `flat-surface`

One line: the working ARIA grid is the majority of the canvas by design — the
title-block is a thin structural cap, the left rail is icon-only chrome, and
the certificate strip only exists once a row is selected. That's a hard break
from surface 1 (login), which is `centered-statement` on presumably a
`tonal-gradient` or `color-block` calm entry — this is the first "busy"
screen in the flow and reads that way immediately. Background is a single
solid substrate with hairline dividers doing the structural work; no texture,
no image, no gradient — the blueprint half of the collision comes from the
stamped-certificate motif and technical-drawing leader lines, not from a
decorative background, so `flat-surface` is the honest token, not
`textured-surface`.

---

## Layout move — exact numbers

### Region map (1440×900)
| Region | Box | Notes |
|---|---|---|
| Sticky header | x 0–1440, y 0–48 | 48px reserved, fixed top, z-above content, 1px hairline bottom border |
| Left rail (rest) | x 0–56, y 48–900 | 56px wide, 852px tall |
| Left rail (hover/focus reveal) | overlay, x 0–208, y 48–900 | absolutely-positioned flyout, does NOT reflow main content — reveal-not-stretch |
| Main content, strip closed | x 56–1440, y 48–900 | 1384×852 |
| Main content, strip open | x 56–1080, y 48–900 | narrows to 1024×852 |
| Certificate strip (conditional) | x 1080–1440, y 48–900 | 360×852, slides in on row select, 1px hairline left border |

### Sticky header (0–48px band)
- App mark: 24×24, centered over the 56px rail column
- ⌘K search/go-to field: x=80, width 320px, **height 40px** (meets primary-control floor), y=4 (4px top/bottom padding inside the 48px band)
- Right cluster: role avatar + notification + theme toggle, 32×32 each (secondary controls), 8px gap, 16px right margin

### Left rail
- Rest: icon buttons **40×40** each (primary nav = primary control, meets the 40px floor), 8px vertical gap, centered in the 56px column, 20×20 icon glyphs
- Hover/focus: overlay expands to 208px; same 40px-tall rows now show 20px icon (16px left inset) + label (body 14px/450); box-shadow `0 4px 16px oklch(0.20 0.01 58 / 0.12)`; main content stays pinned at x=56 — the overlay sits on top, it does not push

### Title-block header (top of main content)
- Padding: 24px left/right, 16px top, 12px bottom
- Line 1 (screen title, 20px/600, line-height 28px): "Finance Manager — Role Home" · right-aligned in same row: bulk-action button "Approve selected" **40px height**, accent-emphasis fill, hidden until ≥1 row is checked (no empty/disabled ghost button sitting there by default)
- Gap: 4px
- Line 2 (section-eyebrow, 12px/600 caps, secondary text): "AS OF 09:00 · 14 AUG 2026 · ACME CORP · 40 ITEMS AWAITING ACTION"
- **Total title-block height: 16 + 28 + 4 + 16 + 12 = 76px**
- 1px hairline bottom border closes the block

### Worklist grid (`role="grid"`, real interactive cells)
- Column header row: y=76, **height 36px**, sticky within the grid's own scroll container, 1px bottom hairline, labels in meta 12px/450 caps
- Data rows: **height 40px** each (border-box, includes 1px bottom hairline `oklch(0.88 0.008 58)`); no zebra fill — hairlines and tabular figures only, per the data-brutalist half of the collision; hover = accent-tint bg at reduced opacity; selected row = 3px left accent-emphasis bar + full accent-tint bg
- Columns, 12px horizontal cell padding, vertically centered:
  1. checkbox — 40px
  2. status chip — 96px (shape+glyph+label, never color alone)
  3. document ID (mono-identifier) — 140px — e.g. `BILL-2026-00042`
  4. vendor — 200px, ellipsis-truncate
  5. amount (tabular-nums, decimal-aligned, right-aligned) — 120px — e.g. `12,480.00`
  6. due date (tabular-nums) — 96px
  7. assignee — 160px (18px avatar + name)
  8. quick actions — 96px (2× 32×32 icon buttons — secondary controls, not held to the 40px floor)
  9. WHY annotation — flex, 220px minimum
- **Leader-line annotation placement**: 1px accent-ink horizontal rule, 20px long, in the gutter between the status-chip cell and the WHY column, with a 4px vertical terminal tick at each end (technical-drawing dimension-line convention — this is where "blueprint" shows up structurally, not decoratively); annotation text in meta 12px/450, 4px right of the line — e.g. "3 days overdue," "awaiting 2nd approval," "GRN mismatch: qty −4"
- **Row count**: ~40 ranked rows (overdue/highest-risk first). Visible without scroll = (852 − 76 title-block − 1 divider − 36 col-header) / 40 ≈ **18 rows**; remaining ~22 reachable by scrolling the grid body only — page chrome (header, rail, title-block) stays fixed

### Certificate strip (opens on row select, 360×852)
- Header, 56px: selected doc's mono-identifier + status chip, 32×32 close button, 1px bottom hairline
- Body, scrollable: vertical timeline spine (1px hairline, accent-ink), 24px from strip's left edge; nodes for PO → GRN → Bill:
  - 8px marker circle on the spine (filled accent-emphasis = complete, hollow/dashed = pending)
  - Node card, 16px right of spine: mono-identifier + doc-type label (meta 12px), status chip
  - **Calibration block** (the collision's namesake move) beneath each node: 4-row key/value stamp, 1px dashed hairline border, 8px padding, each row 20px tall — `MEASURED — 12,480.00` / `TOLERANCE — ±0, matched` / `CHECKED BY — [name]` / `DATE — [timestamp]`
  - 24px gap between nodes
- Footer, 56px, sticky: primary action button, full width minus 24px×2 padding, **40px height**, "Approve Bill" — accent-emphasis fill / white label

### Focus
`:focus-visible` only, 2px solid `oklch(0.42 0.09 58)`, 2px offset — every row, checkbox, rail item, header search, strip buttons.

---

## Type table

| Level | Face | Size | Weight | Line-height | Use here |
|---|---|---|---|---|---|
| Screen title | Inter Variable | 20px | 600 | 28px | title-block "Finance Manager — Role Home" |
| Section eyebrow | Inter Variable | 12px caps | 600 | 16px | title-block as-of line, grid column headers |
| Body/data | Inter Variable, tabular-nums | 14px | 450 | 20px | vendor, amount, due date, calibration values |
| Meta | Inter Variable | 12px | 450 | 16px | WHY annotations, strip labels/timestamps |
| Mono-identifier | IBM Plex Mono Variable, tabular | 13px | 500 | 18px | document IDs only — never for anything else |

## Color table

| Token | OKLCH | Role here | Ratio (as stated in dispatch) | Independent check |
|---|---|---|---|---|
| substrate | `oklch(0.985 0.003 58)` | page/grid bg | — | — |
| primary text | `oklch(0.20 0.01 58)` | headings, mono-identifiers, data values | — | — |
| secondary text | `oklch(0.45 0.012 58)` | eyebrow, meta, column labels | — | — |
| hairline border | `oklch(0.88 0.008 58)` | row dividers, rail overlay edge, Draft dashed border | — | — |
| accent-ink | `oklch(0.42 0.09 58)` | leader lines, focus ring, links | 8.71:1 on substrate | recomputed 8.34:1 — same order, both clear AAA body text; logging the dispatch-stated figure, flagging the ~0.4 delta as rounding in the source matrix, not a transcription error |
| accent-emphasis | `oklch(0.55 0.13 58)` | Approve buttons | 5.06:1 white label on it | recomputed 5.06:1 — exact match |
| accent-tint | `oklch(0.94 0.03 58)` | selected-row bg, badge bg | 7.27:1 w/ accent-ink text | recomputed 7.26:1 — exact match |
| Posted/Active chip | bg `oklch(0.95 0.03 150)` / text `oklch(0.5 0.12 150)` | status | not stated in dispatch | **computed, not rendered — 4.95:1** |
| Error/Overdue chip | text `oklch(0.5 0.18 25)` / bg not given | status | not stated | **computed, not rendered — 5.60:1**, using an assumed tint bg `oklch(0.95 0.03 25)` built on the same pattern as the green pair — see gaps below |
| Pending chip | H≈240° only, L/C not given | status | not stated | **computed, not rendered — 6.18:1**, using assumed text `oklch(0.45 0.08 240)` / bg `oklch(0.94 0.02 240)` — see gaps below |
| Draft chip | "neutral gray + dashed border," values not given | status | not stated | **computed, not rendered — 6.26:1**, using text = secondary-text token / assumed bg `oklch(0.94 0.003 58)` — see gaps below |
| Closed chip | "dark-neutral, label only," values not given | status | not stated | **computed, not rendered — 10.68:1**, using assumed text `oklch(0.98 0.003 58)` / bg `oklch(0.35 0.006 58)` — see gaps below |
| Dark substrate | `oklch(0.18 0.006 58)` | dark mode bg | — | — |
| Dark text | `oklch(0.94 0.006 58)` | dark mode text | — | computed, not rendered — 15.77:1 |
| accent-dark | `oklch(0.72 0.10 58)` | dark mode accent | target ≥4.5:1 | computed, not rendered — 7.40:1, clears target with margin |

## Content direction
One line: every worklist row carries real Atlas vocabulary and the live tenant's actual seed identifiers (`BILL-2026-00042`, `PO-2026-00118`, vendor names, "Acme Corp") — no invented brand, no lorem — and every WHY annotation is a plausible dense-ops reason (days overdue, approval stage, quantity mismatch) at the length a real one runs, never a placeholder string.

---

## Embarrassment-gate self-check
- Palette hexes/OKLCH: every value used above is copied verbatim from the dispatch; nothing substituted. The three dispatch-stated ratios were independently recomputed from the OKLCH triples and match within rounding (8.34 vs 8.71, 5.06 vs 5.06 exact, 7.26 vs 7.27) — logged both, no discrepancy worth flagging as an error.
- Body-size (14px) and meta (12px) type sit on accent-tint/substrate/dark-substrate pairs all ≥6.2:1 in this spec, clear of the 4.5:1 floor.
- Four-band mobile requirement doesn't apply — this is a desktop tool-shaped surface; its equivalent (sticky header reserved, no edge-to-edge chrome) is honored at 48px.
- Collision is legible: the calibration-block motif (measured/tolerance/checked-by/date) appears exactly where the collision sentence puts it — inside the certificate strip's per-node stamps — and nowhere else; the worklist itself stays hairline-and-tabular, not stamped.
- Density claim ("designed load at forty rows") is backed by an actual row count and scroll math (18 visible, 22 scrolled), not an assertion.
- Composition differs from the login sibling by construction (`dense-grid` vs. presumed `centered-statement`).
- No invented brand/logo, no fabricated data-as-claim — dollar amounts and IDs are structural placeholders at realistic length, not presented as real figures.
- Would sign this: yes, with the status-chip background gap below flagged for the palette-keeper rather than silently invented as final.

## Couldn't fully satisfy
The dispatch's STATUS block gives exact OKLCH pairs for Posted/Active only; Error/Overdue gives text-only, Pending gives hue-only, Draft and Closed give neither. I extrapolated backgrounds for those four using the same lightness/chroma pattern as the given Posted pair (L≈0.94–0.95, low C for tints; L≈0.35 for the one dark-neutral chip) and computed their ratios fresh, each marked "computed, not rendered" above — these four background values need palette-keeper confirmation before build, they are not sourced from DIRECTION.md.
