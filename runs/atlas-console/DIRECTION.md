# DIRECTION.md — atlas-console (porcelain · COMPLETE — Loop 1 direction + Loop 2 craft)

Direction half by `direction-conductor` (Loop 1); craft half by `craft-conductor` (Loop 2,
2026-08-14, prototype evidence in `prototypes/*.verdict.md`). Gate A DECIDED by Taha
2026-08-14: **porcelain**, one word, no caveats. Rounds 1 and 2 rejected in full
(`rejected-v1/`, `rejected-v2/`). Gate B is pending — this file plus `tokens.json` plus the
prototype screenshots are the package presented there; nothing in it is self-approving.

**Test this file is written against:** could a build agent execute this without making a
single aesthetic decision? Rows that still fall short are named honestly in §25.

**Suspension record (BREAKING.md out-loud rule):** `PRINCIPLES.md` §1–§3's invent-everything
mandate is suspended for this run per TRANSLATE.md's recorded decision — both rejections
shared one failure, an invented concept metaphor, and the user's nine references ARE the
register. User instructions outrank skill defaults. Distinctiveness comes from execution
quality and ERP-specific information design, not an invented metaphor. Consequently: no
derivation, no multiple concepts, no distinctness tests, no rejected-concept exhibit.

**Classification:** reposition (human-confirmed). Survival list honored: Inter Variable
self-hosted (kept, load-bearing), terminology lock (item / vendor / customer / warehouse /
journal entry), route structure untouched.

**Sources:** approved visual `gate-a-approved-porcelain.html` (`.po`/`.po.dark` blocks);
refs 4 (Salung), 7 (Untitled UI), 9 (TrustToken), 2, 6 (glass layers); live-app extraction
2026-08-14; `design/porcelain/_register.md` (worker source of record — where it and this
file differ, this file wins).

---

# PART I — DIRECTION (Loop 1, amended ◆ where Loop 2 measured)

## 1. Surface class · platform mode

**tool-shaped** (TRANSLATE.md row 1). Platform mode **skipped, by decision**: web-only,
desktop-only; every operator role is a desk role; `SURFACES.md` §1 not triggered. Recorded
with its risk in §11 (RISK 4). ◆ Loop 2 consequence: the budget measurement condition is
desktop Chrome at 4× CPU throttle, not a mid-range Android — a recorded deviation from the
loop file's default, justified by this decision.

## 1a. Collision / subversion

None invented, under the recorded suspension. The structural parent is the user's own
reference register — Untitled UI's sidebar anatomy × Salung's mono-caps-and-ink-button
voice × the glass ⌘K layer of refs 2/6 — executed at spec resolution on ERP content. That
sentence is the whole concept; the register is conformed to, not collided with.

## 2. The direction — porcelain

Light-led, near-monochrome, quietly polished contemporary product register; full dark theme
as a first-class equal (both themes comped for every surface). Sidebar 248px with workspace
switcher, mono-caps section labels, pill active states, count badges, pinned user card
(ref 7). Mono-caps labels (JetBrains Mono 10.5px/600/.06em) on stat cards, panel heads,
table headers; ink-black primary button with white text (ref 4). Soft tinted status pills,
dot + label, never color alone. Sparklines in stat cards; monochrome paired-bar chart —
the accent is never a data color. **One blue accent** (#3f5bf6 light / #93a5ff dark)
carrying links, active nav, focus, filter chips; everything else neutral. **Glass confined
to floating layers only** — the ⌘K palette (keycap chips, ref 6) and popovers; nothing
structural ever blurs; reduced motion degrades the blur-in to an instant fully-opaque
panel, a designed state.

**Modes, declared: one design in two palettes** — same composition, same anchors, per-mode
retuning of material only. The named per-mode deltas: shadow color/opacity (§17), glass
border (40% card + #ffffff88 light → 14% white dark), accent lightness (55% → 74.5% L),
scrim depth (32% ink light → 48% black dark), status tint inversions. Light direction of
shadows identical in both modes. Not two art directions: porcelain is not atmospheric,
motion-native, or material-heavy — the CRAFT.md trigger for two art directions does not
fire, and the declaration is made rather than implied.

## 3. Palette — script-verified pairs (WCAG 2.x, computed 2026-08-14; not estimated)

38 pairs computed by script (`scratchpad/contrast.py`); ◆ Loop 2 added 11 confirmations
(T5 verdict) and two rendered worst-case measurements (T1 verdict). One adjustment to the
approved starting values, logged:

| Pair | Token | Before → After | Ratio before → after |
|---|---|---|---|
| warn-tx on warn-bg (light) | warn-tx | `#96660f` → **`#94650c`** | 4.46 → **4.54** |

One 0.005 OKLCH L step, hue and chroma held. Also dropped: the approved HTML's
`--ink3:#9becb0` — a dead variable (mint mislabeled as a neutral, referenced by zero
rules); removal logged, no design decision reversed.

### Light

| Token | Value | OKLCH | Paired foreground → measured ratio (floor) |
|---|---|---|---|
| bg | `#f7f7f8` | `oklch(97.6% 0.001 286.4)` | ink 16.57 · ink2 4.814 · acc 4.86 |
| card | `#ffffff` | `oklch(100% 0 0)` | ink 17.74 · ink2 5.15 · acc 5.20 · ok-tx 5.37 · bad-tx 6.16 · warn-tx′ 5.09 |
| ink | `#17181c` | `oklch(21.0% 0.008 274.5)` | white on it (ink button) 17.74 |
| ink2 | `#6b6d76` | `oklch(53.6% 0.014 275.9)` | ◆ never directly on glass (T1: worst-case rendered 3.98) |
| line | `#e9e9ee` | `oklch(93.5% 0.007 286.3)` | decorative only (1.21 vs card) — never the sole boundary/state signal; ◆ never a data-bar fill (T3) |
| acc | `#3f5bf6` | `oklch(55.0% 0.232 269.1)` | on acc-t 4.580 · focus ring vs bg 4.86 (3.0) · sparkline vs card 5.20 (3.0, ◆ rendered-pixel confirmed) |
| acc-t | `#edf0fe` | `oklch(95.7% 0.019 276.3)` | ◆ ink on acc-t **15.62** (script-confirmed; replaces hand ≈15.7) |
| ok-bg / ok-tx | `#e7f6ed` / `#177a48` | `oklch(96.0% 0.020 159.8)` / `oklch(51.3% 0.118 155.2)` | pill 4.804 |
| warn-bg / **warn-tx′** | `#fbf1de` / **`#94650c`** | `oklch(96.1% 0.027 83.5)` / `oklch(54.3% 0.110 75.8)` | pill 4.542 |
| bad-bg / bad-tx | `#fbe9e7` / `#b23425` | `oklch(94.8% 0.020 25.2)` / `oklch(51.3% 0.165 30.3)` | pill 5.251 |
| ◆ bar-lo (proposed) | `#939599` | `oklch(66.9% 0.007 275)` | vs card **3.0002** (3.0) — Gate B choice, §19 |
| shadow | `0 1px 2px rgba(23,24,28,.04), 0 10px 28px -8px rgba(23,24,28,.09)` | — | — |
| glass composite | ◆ RENDERED (T1): calm 17.44; worst-case busy frame: ink **8.02**, kbd chip 17.74, highlighted row 16.41, ink2 **3.98 (fails — constraint §14)** | — | — |

### Dark

| Token | Value | OKLCH | Paired foreground → measured ratio (floor) |
|---|---|---|---|
| bg | `#131418` | `oklch(19.2% 0.008 274.5)` | ink 15.91 · ink2 6.74 · acc 7.95 |
| card | `#1b1c22` | `oklch(22.8% 0.012 278.0)` | ink 14.68 · ink2 6.23 · acc 7.34 · ok-tx 9.76 · warn-tx 8.98 · bad-tx 7.37 |
| ink | `#eeeef2` | `oklch(95.0% 0.005 286.3)` | `#17181c` on it (ink button, inverted) 15.33 |
| ink2 | `#9a9ca8` | `oklch(69.5% 0.018 278.4)` | ◆ never directly on glass (T1: worst-case 4.59 — rule mode-symmetric) |
| line | `#2a2c35` | `oklch(29.5% 0.017 275.5)` | decorative only (1.22 vs card) |
| acc | `#93a5ff` | `oklch(74.5% 0.132 274.2)` | on acc-t 6.46 · focus ring vs bg 7.95 · sparkline vs card 7.34 (◆ rendered-pixel confirmed) |
| acc-t | `#232637` | `oklch(27.4% 0.032 276.4)` | ◆ ink on acc-t **12.93** (script-confirmed) |
| ok-bg / ok-tx | `#1b2f24` / `#7fd6a4` | `oklch(28.4% 0.033 159.3)` / `oklch(80.7% 0.111 157.5)` | pill 8.154 |
| warn-bg / warn-tx | `#332a17` / `#e4b566` | `oklch(29.0% 0.034 85.0)` / `oklch(79.9% 0.111 79.1)` | pill 7.478 |
| bad-bg / bad-tx | `#361f1c` / `#eb9486` | `oklch(26.8% 0.037 27.8)` / `oklch(75.2% 0.108 29.7)` | pill 6.653 |
| ◆ bar-lo (proposed) | `#66676b` | `oklch(51.3% 0.007 275)` | vs card **3.0081** (3.0) — Gate B choice, §19 |
| shadow | `0 1px 2px rgba(0,0,0,.3), 0 10px 28px -8px rgba(0,0,0,.4)` | — | — |
| glass composite | ◆ RENDERED (T1): calm 14.67; worst-case: ink **5.00**, kbd chip 14.68, highlighted row 13.37, ink2 4.59 | — | — |

◆ **The no-headroom rule (T5):** acc-on-acc-t 4.580, warn′ pill 4.542, ink2-on-bg 4.814,
and both bar-lo values sit at their floors with zero margin. **Any future tint change
re-runs `scratchpad/contrast.py` before it lands.** Disabled text: ink2 at 55% opacity,
contrast-exempt, never the only disabled signal.

One accent for the run (`PRINCIPLES.md` §6): both themes' accents are the same
periwinkle-blue family sampled from the references themselves; re-sampling terminated at
Gate A's decision.

## 4. Status vocabulary

Pill: h24, radius-full, 12px/500, 7px currentColor dot + 5px gap, dot + label always —
never color alone. Draft is the shape-distinct variant: transparent fill, 1px dashed line
border, ink2 text, no dot. ◆ Grayscale-proof screenshotted (T5 `gray` states): state fully
legible at zero hue.

| Variant | Light | Dark | Labels in use |
|---|---|---|---|
| ok | `#177a48` on `#e7f6ed` (4.804) | `#7fd6a4` on `#1b2f24` (8.154) | In stock · Posted · Paid |
| warn | `#94650c` on `#fbf1de` (4.542) | `#e4b566` on `#332a17` (7.478) | Low stock · Pending · Partially paid |
| bad | `#b23425` on `#fbe9e7` (5.251) | `#eb9486` on `#361f1c` (6.653) | Out of stock · Mismatch · Overdue · Reversed |
| mute (dashed) | ink2, dashed line border | same | Draft |

Vendor-bill mapping (decision, recorded): Draft=mute · Posted=ok · Partially paid=warn ·
Paid=ok · Reversed=bad. Posted vs Paid distinguished by label, not hue.

## 5. Type system — role-indexed scale (declared; not a ratio)

The scale is **role-indexed** — twelve named roles, each tied to a job, chosen against ERP
density rather than derived from a modular ratio; a ratio would be a false claim here and
is not made. Rem equivalents at 16px root. Measures: table cells truncate with full value
on hover/focus (`title` + tooltip); centered statements (06/07) max-width **52ch**; form
column (05) **560px**; running prose (rare) max **72ch**.

| Role | Face | px / weight / lh | rem | Reason on the line |
|---|---|---|---|---|
| h1 / page title | Inter Variable | 22/650 −0.01em lh28 | 1.375 | one per screen; full weight axis carries hierarchy in one file |
| stat value | Inter Variable | 26/650 tnum lh32 | 1.625 | tabular figures align stat columns; ◆ T4: unit `<small>` must not sit on flex-baseline (build note §23) |
| body / table | Inter Variable | 13/450 lh20 | 0.813 | the register's working size; tnum in all data cells |
| nav / palette rows | Inter Variable | 13.5/500 (550 active) | 0.844 | |
| sub / meta | Inter Variable | 12–13/450 ink2 | 0.75–0.813 | |
| delta / fine | Inter Variable | 11.5/450 | 0.719 | |
| pill | Inter Variable | 12/500 | 0.75 | |
| statement | Inter Variable | 15/500 | 0.938 | empty/error voice; the one size between body and h1 |
| mono-caps label | JetBrains Mono Variable | 10.5/600 .06em uppercase | 0.656 | signature label voice (refs 4/7); monospace keeps caps tracking even |
| identifier | JetBrains Mono Variable | 11/500 | 0.688 | ITM-/BILL-/PO- codes scannable, never prose |
| title-identifier | JetBrains Mono Variable | 20/600 in 28px h1 line box | 1.25 | a document's name IS its identifier (04) |
| kbd chip | JetBrains Mono Variable | 11/450 | 0.688 | |

Both faces self-hosted. ◆ Inter Variable latin woff2 exists in repo at 48,256 B (TESTED).
◆ JetBrains Mono Variable is NOT in the repo — vendoring is a build task; subset to
caps + digits + symbols (mono roles use no lowercase); budget contingency in §20. Fallback
stacks: system-ui / ui-monospace (the approved HTML's own stacks). Tabular figures declared
on every data-bearing number. ◆ Mono metrics: prototype geometry carried the fallback face;
expect ±2px line-box change when JBM lands — re-measure row heights (T5).

## 6. ACCESS.md §13 — 19 of 23 answered; 4 native rows N/A

(Carried from Loop 1 in full — see prior revision for the complete 19-row table; deltas
Loop 2 adds are listed here and bind over it.)

| # | Decision | Answer (Loop 1, unchanged except ◆) |
|---|---|---|
| 1 | Target size | 44px floor for standalone primaries; approved page-head controls keep 38px visual + 44px extended hit target; dense row-action clusters WCAG 2.5.8 ≥24px c-to-c (◆ measured 59–65px, T5); compact rows ≥36px (◆ real: 59px, two-line cells — §13.6) |
| 2 | Contrast boundary | 18px/14px-bold large-text line (3:1); everything under is body (4.5:1) |
| 3 | Accent capability | measured: light 5.20/4.86, dark 7.34/7.95; accent never a data color, never text-on-accent fill |
| 4 | Focus indicator | 2px solid acc, 2px offset, `:focus-visible` only — 4.86/7.95 vs bg; checked vs card, acc-t, glass |
| 5 | Sticky chrome | no structural glass; sticky table headers reserve 56px; glass layers floating + modal, focus-trapped |
| 6 | Drag affordance | no drag surface; future kanban gets "Move to…" per card |
| 7 | Auth path (3.3.8) | password auth; paste + managers never blocked; no cognitive CAPTCHA |
| 8 | Help slot | last item of sidebar's second section, every screen |
| 9 | Landmarks | one h1 per screen; one main; one nav "Primary"; skip link first, visible on focus (omitted on 01 only, reasoned) |
| 10 | Accessible names | per-record names ("More actions for ITM-BOLT-M6X20"); the full string list is §13.8 |
| 11 | Reduced motion | palette blur-in → instant fully-opaque panel (◆ built + screenshotted, T1); skeleton shimmer → static (◆ built, T4); nothing else moves |
| 12 | Script/direction | LTR Latin; tightest string sized in 04 |
| 13 | Focus on route change / removal | route change → h1 tabindex −1; removed row → next row, or table if empty |
| 14 | grid contract | full contract in 03: roving tabindex, arrows/Home/End/Ctrl+Home, Enter, Esc, Space, Shift+arrow |
| 15 | Combobox popup | listbox, flat options; ⌘K palette reuses it (◆ keyboard pass TESTED green in T1: trap, arrows+wrap, Esc+focus return) |
| 16 | Modal initial focus | least-destructive (Cancel); invoker-gone fallback → next row/table |
| 17 | Menu, really? | sidebar stays plain nav; the one real `menu`: row "⋯" overflow |
| 18 | Live regions | silent: hover, palette open. Polite: saved, counts. Assertive+focus: expiry, failed save, conflict |
| 19 | ARIA cost lines | grid · listbox combobox · modal dialog · overflow menu · status/alert live regions |

◆ **New constraint from T1 (binds every glass layer):** text directly on glass renders
**ink only**; ink2 appears solely on opaque backings (kbd chips, highlighted rows, the
query input's card fill). The palette empty-state hint therefore renders ink, not ink2.

## 7. Nine data states — designed, not deferred

loading → 02 (skeleton stats/panels), 03 (skeleton rows), 04 (**bounded** skeleton: data or
error, never the live app's infinite "Loading…"). ◆ Skeleton discipline proven: CLS 0,
geometry Δ 0.00px (T4). true-empty → 06 variant + 02's "Nothing needs you right now."
filtered-empty → 06 proper (chips stay, Clear filters 44px primary, "0 of 214 shown").
sparse → 03 (8 of 214, honest pagination). dense → 03 (compact mode; forty rows change
scroll, nothing else). error → 07 (bad-ID: "This record wasn't found. Nothing was
changed."), 01 (bad credentials, input preserved), 05 (per-field validation + alert
summary), 07a (failed fetch + Try again). permission-denied → 04 ("Posting requires
finance.ap.manage — ask an admin."), 07b (403 route). conflict → 04 (both versions side by
side, keep-mine/keep-theirs, focus moved, alert). in-flight → 01 "Signing in…",
04 "Posting…", 05 "Creating…" — input never lost.

Render states cross these (tool-with-motion owes both axes): the two moving techniques
(palette, skeleton) each ship full + reduced + no-backdrop-filter/no-shimmer renderings —
built and screenshotted in T1/T4. No WebGL exists; context-loss states are N/A.

## 8. Style under density

*At forty rows porcelain does nothing new — pills, mono-caps headers, and tabular figures
are flat per-row cost, density lives inside one bordered panel rather than forty cards, so
the only thing that changes is row height stepping to compact — and the glass palette never
meets density at all, because it floats above the list instead of living in it.*
◆ Measured at 40 and 200 rows (T5): default row 65px, compact 59px (two-line item cells;
the old "36px" arithmetic assumed single-line rows — 36 remains the floor for single-line
tables), pill 24px exact, centering offset 0.

## 9. Composition log + set-level check

| Surface | Anchor | Background |
|---|---|---|
| 01 login | centered-statement | flat-surface |
| 02 role home | left-rail-caption | flat-surface |
| 03 items list | dense-grid | flat-surface |
| 04 vendor bill detail | right-rail-caption | flat-surface |
| 05 new item form | stacked-center | flat-surface |
| 06 empty (filtered) | centered-statement (inside work chrome) | flat-surface |
| 07 error | centered-statement | flat-surface |

Anti-repeat criteria suspended under the tool-shaped carve-out (no page-shaped subset);
never-vary list checked and passes: one palette, one type system, one component family
across all 7 surfaces and both themes. Disclosure: the set-level pass is
conformance-checking, not independent composition (workers shared this conductor's
register), recorded as the weaker instrument.

## 10. Worker flags → conductor rulings (Loop 1, carried)

1. 02 palette query-input row: legitimate refinement — typed-query state adds row-0 input
   (open height 198 → 242); approved geometry recorded beside it. Gate-B-visible.
   ◆ Loop 2: built in T1; the input carries an opaque card fill so its ink2 placeholder is
   legal (§6 constraint).
2. 02 11.5px vendor sub-lines vs 11px identifier role: as-approved, kept.
3. 03 ink-on-acc-t pairs: ◆ CLOSED — script-confirmed 15.62 / 12.93 (T5).
4. 03 approved frame's filter chips contradict visible rows/count: kept verbatim; Loop 2+
   renders real data and the contradiction dissolves.
5. 03 density toggle placement (pagination row): accepted extension; 06 omits at zero rows.
6. 05 input borders below 3:1: accepted register property — ruling upheld at Loop 2 and
   recorded as the one broken-rules row (§19).
7. 05 page height 1270: forms scroll; fold documented.
8. 06 15px/500 statement line: adopted into §5.
9. 06 true-empty pagehead: chrome parity binds filtered-empty proper only.
10. 04 document-flow chain: designs the promised chain; identifiers marked API-bound.

## 11. SAFE / RISK (carried; ◆ status updates)

**SAFE:** a twice-corrected, human-approved register executed at spec resolution with
script-verified contrast; both themes real; system-stack fallbacks mean nothing breaks if
a font fails.

**RISK 1 — restraint decays into the rejected "bland dry ERP."** Signature set (mono-caps
rhythm, ink button, sparklines, two-layer shadow, the one glass moment) is never-cut.
Cost if flattened: a third full rejection, after approval, spending trust. ◆ Loop 2 kept
all five signatures; every prototype executed them at token resolution.

**RISK 2 — the glass palette is the register's one fragile object.** ◆ Substantially
retired: worst-case text contrast now RENDERED (ink 8.02/5.00 passes; ink2 fails →
constraint §6, not a surprise at build), fps measured at 4× CPU throttle (89/88 median),
and the weak-GPU floor (opaque panel) is built and pixel-verified identical to the
reduced state. Residual: low-end Windows iGPU cost — PARTIAL, §21.

**RISK 3 — dual-theme support doubles surface QA forever.** Accepted knowingly at Gate A.
◆ Loop 2 paid it: every prototype state screenshotted twice; every new value (bar-lo,
state fills) computed twice.

**RISK 4 — desktop-only assumption + a second font file.** ◆ Sharpened: JBM is not in the
repo; subset + vendoring is a build task with a pre-decided tier-2 contingency (§20). A
real tablet requirement still forces a §13 re-answer.

## 12. Coded-comp disclosure (◆ amended)

The 14 comps remain coded specs. ◆ Loop 2 rendered the first porcelain pixels outside the
approved board: five prototypes, both themes, 40+ screenshots. The glass "computed, not
rendered" caveat is CLOSED for the palette (worst-case rendered numbers above). Surface
comps' ratios remain computed-against-cited-hexes; the build renders them.

---

# PART II — CRAFT (Loop 2)

## 13. TOOLS.md §13 — the nine deliverable items

### 13.1 The day, per role — with counts (ESTIMATED from module shape + seed data; no
operator interview exists — deferral §21)

**Amira K., Buyer · Procurement (primary persona):** signs in 08:00 (01 → 02). Reads the
role home ~5×/day — four stats, needs-action list. The items list (03) is the working
surface: opened ~40×/day, filtered or searched almost every time; the repeated read is
scanning status pills for Low stock / Out of stock. ⌘K ~30×/day (jump to record, receive
stock, new PO — the palette's three accelerator rows). Creates or edits items 2–3×/day
(05). Touches vendor bills 4–6×/day (04); posting is gated on `finance.ap.manage` — she
sees the permission-denied explainer, not a missing button. Hits filtered-empty (06)
weekly; errors (07) rarely. Interrupted constantly: every screen survives leave-and-return
— filter/sort/search state in the URL, no unsaved work trapped in modals.

**Finance (AP) role:** opens 04 ~20×/day, posts 5–10 bills; the conflict state (two people
on one bill) and "Posting…"-with-input-preserved are their day's real states.

Consequence: assignment of craft budget followed these counts — 03, the palette, and 02
got the techniques; 01/05/06/07 stay quiet (§15).

### 13.2 Screen inventory

01 login (enter) · 02 role home (orient + act on exceptions) · 03 items list (the 40×/day
work surface) · 04 vendor bill detail (read + post + conflict) · 05 new item form (create)
· 06 filtered-empty (recover from over-filtering) · 07 error family (bad-ID / failed fetch
/ 403). Each exists as light+dark comps in `design/porcelain/`.

### 13.3 Key flows with the nine states — §7 above maps every state to its surface.

### 13.4 Keyboard map

Global: **⌘K** opens the palette from anywhere (query mode from the search field, actions
mode from bare invocation); **Esc** closes/backs out, returns focus to invoker; **Enter**
is every form's primary action; skip link is the first tab stop. Palette accelerators,
discoverable as keycap chips on their rows: **⌘N** new item · **⌘R** receive stock ·
**⌘B** pay vendor bill. Items list (03): the full grid contract (§6 row 14). Form (05):
Enter submits "Create item"; Esc warns if dirty. Modals: trap, Esc, focus return.
Decision, recorded: **no separate "?" shortcut overlay this phase** — discoverability is
carried by the keycap chips inside the palette and the ⌘K chip on the search field; an
overlay is a new surface this register does not owe yet.

### 13.5 Design system — `tokens.json` (DTCG, beside this file) + §4 status vocabulary +
data display set: money `USD 54.00` (code + amount, tnum, right-aligned) · date
`Jun 20, 2026` · empty `—` (em-dash universal) · identifier mono 11px uppercase · person
"Amira K." + role sub-line · quantity right-aligned tnum. Each formatted one way,
from one component.

### 13.6 Density decisions — default row **65px**, compact **59px** (measured, two-line
cells; 36px floor applies to single-line tables); toggle lives in the pagination row
(table-owned chrome), absent at zero rows; density changes scroll, nothing else. Column
choice/order/width per operator: deferred to a later module pass, recorded.

### 13.7 Mobile and field — N/A by decision (§1, RISK 4).

### 13.8 Copy — canonical strings

"Nothing needs you right now." (02 empty) · "No items yet. Create your first item." + New
item (06 true-empty) · "0 of 214 shown" + Clear filters (06) · "This record wasn't found.
Nothing was changed." (07) · "Couldn't load this page. Try again." (07a) · "Posting
requires finance.ap.manage — ask an admin." (04/07b) · "Signing in… / Posting… /
Creating…" (in-flight) · conflict: "Keep mine" / "Keep theirs" (04) · palette empty: "No
results for "…"." + "Check the identifier, or press Esc to close." (ink, not ink2 — §6).
Accessible-name strings: "Open command palette (⌘K)" · "More actions for {identifier}" ·
"Remove filter: {label}" · "Switch workspace" · "Search items (⌘K)". Buttons say what they
do: "Create item", "Post bill", never "Save"/"Submit".

### 13.9 Accessibility notes — §6 in full; plus: focus order follows visual order
everywhere; route announcements via h1 focus; the two moving techniques honor
reduced-motion at both layers (CSS + matchMedia listener).

## 14. Remaining schema rows, at rendered resolution

**Spacing** — base 8px, 4px half-steps; ladder with jobs in `tokens.json` `space` (4 · 8 ·
10 · 12 · 14 · 16 · 18 · 24 · 28 · 36). Margins cap at 28/36 and stop growing past
desktop — this run's own ladder, declared as invented, no system claimed.

**Radius** — 6 (kbd/skeleton) · 9 (nav) · 10 (controls) · 12 (user card) · 14
(cards/panels) · 16 (overlays) · 999 (pills). Concentric rule in use: inner = outer − gap
(kbd r6 = palette r16 − pad 10). Recorded deviation: palette rows keep approved r10 — an
interaction highlight, not a nested container.

**Stroke and divider** — 1px `line` per mode, decorative only. Table hairlines are
single-edge bottom borders (last row none): horizontal-only rules cannot double by
construction. Any future cell-matrix uses `display:grid; gap:1px` over a line-colored
track, never per-cell borders. No hairline weight change between modes: the line token is
retuned per mode instead (values §3).

**Elevation** — three resting levels, no more: **0** flush (bg; bars at rest, sidebar) ·
**1** card/panel (1px line border + shadow.card — border and shadow together are the
depiction) · **2** floating overlay (palette, popovers, menus, modals: border +
shadow.overlay). Hover/selection never changes elevation — it changes fill (state tokens),
so nothing needs a level to rise to. Modals add scrim (light ink@32%, dark black@48%);
the glass palette floats without a page scrim, as approved. This direction has no other
shadow language.

**Background and surface treatment** — flat surfaces everywhere: no gradients, no grain,
no noise, no generated imagery, no photographs (`§8`/`§14` have nothing to treat). The one
material moment is the glass composite: 62% card + blur(18px) saturate(150%), border 40%
card + #ffffff88 (light) / 14% white (dark), values fixed above.

**Icons** — source: project-owned inline SVG symbol set (the approved board's 15 glyphs:
grid, box, cart, dollar, users, chart, bell, search, plus, gear, chev, file, out, tag,
bolt), licence: original to this repo, no external dependency. 24px design grid, stroke
1.7 at viewBox scale — rendered ≈1.06px at the 15px size, ≈1.28px at 18px (the approved
hairline look, recorded as such), round caps/joins, `currentColor`. No grade axis exists;
per-mode grade compensation is intentionally none — recorded choice (CRAFT's grade rule
targets variable icon fonts; this is a fixed-stroke set). Pairs per input method (mouse+
keyboard primary): 15px icon / ≥40px standalone target; row clusters ≥24px c-to-c
(measured 59–65px). Every nav icon has a visible label; every icon-only control has a
per-record accessible name (§13.8).

**Grid and layout** — pane-based, no column grid claimed: fixed 248px nav pane + fluid
main pane, pad 28/36, content 1120px at the 1440×900 design canvas. Stats 4-col gap 16;
panels 1.2fr/1fr gap 16. Supported range 1200–2560: 4-col and 2-panel hold to 1200; at
≥1700 the content column caps at 1320px (left-anchored in the pane); **below 1200 the
shell holds min-width 1200 and scrolls horizontally rather than reflowing** — the honest
rendering of the desktop-only decision, recorded under RISK 4.

**Navigation model** — persistent sidebar (pattern: rail-with-labels, ref 7 anatomy):
workspace switcher, two labeled sections, count badges, pinned user card, help slot (§6
row 8). Keyboard contract §13.4. State at every supported width: fully visible, never
collapses (no breakpoint exists that hides it). No swipe surfaces exist (desktop web);
system back is the browser's, untouched.

**Content presentation** — panels + real tables + definition lists, per-item attribute
positions fixed in the comps and `_register.md` §3 (item cell = name over mono identifier;
numeric cells right-aligned tnum; status column fixed-width w96).

**Buttons and controls — all seven states, token per state** (values in `tokens.json`
`color.*.state`):

| Control | default | hover | focus-visible | active | disabled | error | loading |
|---|---|---|---|---|---|---|---|
| ink button | btn-ink / btn-ink-tx | btn-ink-hover | +2px acc ring, 2px offset | btn-ink-active | card fill, line border, ink2@55% | n/a (field-level) | fill unchanged, verb + spinner, aria-busy, input locked |
| chip button | card + line border | surface-hover | acc ring | surface-active | ink2@55%, border 55% | n/a | as ink button |
| nav row | ink2 text | surface-hover | acc ring | acc-t + acc text (=selected) | ink2@55% | n/a | n/a |
| input | card + line border | input-border-hover | acc ring + acc border | — | bg fill, ink2@55% | input-border-error + message + aria | value locked, spinner in field |
| table row | card | row-hover | acc ring (grid cell) | row-selected (acc-t) | — | — | skeleton row |
| pill | §4 | none (static) | n/a (not interactive) | — | — | — | — |
| filter chip | acc-t + acc | surface-hover under tint | acc ring | dismiss ✕ | — | — | — |

## 15. Per-surface technique — verdicts and evidence

Arsenal groups assigned from, by name: **CSS and SVG native** and **Information design**.
Nothing from Rendering/GPU or Post-processing. Three-question answers recorded before
dispatch in `craft-draft.md`; full verdicts beside each prototype.

| Surface | Technique | Verdict | Evidence | Byte cost (raw/gzip) |
|---|---|---|---|---|
| 02 + global | T1 glass ⌘K palette | **ship-with-caveat** — caveat: ink2 never directly on glass (3.98 worst-case light); ink passes 8.02/5.00 | TESTED (contrast, fps@4×CPU, keyboard, bytes) · **PARTIAL (low-end GPU fleet — untestable here; floor = opaque panel, built)** | 3,567 / 1,310 B |
| 02 | T2 SVG sparklines | **ship** | TESTED (rendered stroke = token, 0px layout delta, bytes) · PARTIAL (DPR-2 crispness — no instrument) | 209 B/element |
| 02 | T3 monochrome paired bars | **ship** — recommending bar-lo over approved line-gray (1.21:1 fails 3:1); **Gate B chooses** | TESTED (ratios, rendered pixels, real value→height mapping, 12-mo density) | ~3.5KB / 2,336 B file |
| 02/03/04 | T4 skeleton match | **ship** | TESTED (CLS 0, geometry Δ 0.00px ×49, shimmer compositor-proof at 1×/4×/6× throttle) · PARTIAL (paint-count trace) | 1,064 / 646 B |
| 03 + lists | T5 status pills @ density | **ship** | TESTED (geometry, bytes, 11 contrast pairs, rendered pixels) · **PARTIAL (scroll fps — unthrottled only)** · INFERRED (mid-range no-jank — Gate B buys or re-tests) | 506 / 280 B |
| 01, 05, 06, 07 | quiet — base register, no technique | by decision (§13.1 counts) | — | 0 |

**Machine behind every measured number:** Apple M4, macOS 26.5.2, headless Chromium,
1440×900 @ DPR 1; throttled numbers via CDP 4× CPU (T1, T4 — T4 verified 4.28× engaged).
A ship on a PARTIAL or INFERRED line is a proposal, not a proof — the human buys it at
Gate B or orders the re-test.

**No technique was cut.** All five passed. The nearest miss was T1, whose caveat became a
binding constraint (§6) rather than a cut.

## 16. Motion spec — numbers, not adjectives

Named curves (defined once in `tokens.json`, referenced everywhere):
`settle = cubic-bezier(0.2, 0, 0, 1)` (enters, state changes) · `leave =
cubic-bezier(0.3, 0, 1, 1)` (exits).

| Interaction class | Duration | Curve | Properties |
|---|---|---|---|
| micro state change (hover/active/focus/pill) | 120ms | settle | fill/color/opacity |
| overlay enter (palette, popover, menu) | 160ms | settle | opacity 0→1 + scale .98→1, origin top center; **backdrop-filter constant, never animated** |
| overlay exit | 110ms | leave | opacity→0, no scale (exit < enter) |
| skeleton→content swap | 120ms | settle | opacity crossfade, no movement (CLS 0, measured) |
| skeleton shimmer | 1600ms linear loop | — | transform:translateX on overlay only (compositor-proven) |

**Stagger: none, by decision** — tool-shaped lists never stagger in; palette rows arrive
with the panel as one unit. **Triggers:** pointer/keyboard and ⌘K only; no scroll-triggered
motion exists in this register, so no IntersectionObserver is needed and no scroll listener
is permitted. **Nothing animates in above the fold** — no entrance animation on any
surface. **Motion never gates information** — every state readable at t=0.

**Reduced motion, art-directed per technique** (§10 HARD; honored at CSS media-query AND
matchMedia-listener layers, with mid-session change respected):
- palette → instant, fully opaque card panel; no blur, no scale, no fade; same geometry
  and content. Built, screenshotted (`prototypes/shots/glass-palette-reduced-*.png`),
  pixel-identical to the no-backdrop-filter fallback (cmp-verified).
- skeleton → static line-token blocks, no shimmer (`skeleton-reduced-*.png`).
- micro → transform removed; opacity/color fades ≤120ms retained (movement replaced with
  fades; no blur exists to animate — Apple's two never-removed offenders are absent by
  construction).
- sparklines, bars, pills → static by construction; no delta exists.

## 17. Budgets — both tiers, both as numbers

**Measurement condition (declared deviation):** desktop Chrome, 1440×900, 4× CDP CPU
throttle — not a mid-range Android, because this run recorded desktop-only (§1). Where no
throttle instrument existed, the number's label says so (T5).

**Tier 1 — shell: ≤100KB total. Paints real content with no JS. LCP <1.5s.**
HTML ≤12KB · critical CSS ≤18KB (all five techniques' CSS ≈ 5.5KB raw of that) · Inter
Variable latin woff2 **48,256B (TESTED, on disk)** · JetBrains Mono subset ≤18KB
(caps+digits+symbols — mono roles use no lowercase; INFERRED until the build runs the
subsetter) · boot JS ≤4KB. **Contingency, pre-decided:** if the JBM subset cannot reach
18KB, JBM moves to tier 2 and the ui-monospace stack paints first (`font-display: swap`) —
the register's own fallback tier, not an accident. Tier 1 failing is a run failure.

**Tier 2 — heavy: ≤250KB gzipped JS total** (React 18 + TanStack Query/Router + app code,
route-split). Loads after first paint, never in the LCP path. Contains **zero GPU, chart,
or motion libraries** — every Loop 2 technique is tier-1 CSS/SVG. The register's only GPU
feature is `backdrop-filter` on the palette (measured: ~0–4 fps median cost on the test
machine at 4× CPU; fleet floor = opaque panel). Nothing here requires deferral gymnastics:
there is no heavy scene, no poster, no intersection gate to build.

## 18. What was invented

At concept level: nothing, by the recorded suspension — the §3 obligation is discharged by
that record. Run-level refinements, each Gate-B-visible: the typed-query palette row
(ruling 1), the density toggle (ruling 5), the `bar-lo` data-gray pair (T3, pending),
the ink2-never-on-glass constraint (T1), and the measured skeleton discipline (CLS 0 /
Δ 0.00px as an acceptance test, T4). Executions, not metaphors.

## 19. Broken rules

| rule broken | what it buys | what it costs | why the trade is honest here |
|---|---|---|---|
| ACCESS.md 3:1 non-text floor (WCAG 1.4.11) — input boundaries drawn with the 1px `line` token (~1.2:1 vs card) | The approved register's quiet field treatment — the twice-rejected user chose this register with these fields in it | Low-vision operators cannot see field extents until focus arrives or a label anchors them | Identification is carried by always-visible labels above fields + the 4.86/7.95 focus ring; inherited from the approved frames, flagged by the 05 worker rather than smuggled, upheld here as a recorded ruling, and presented at Gate B where it can be reversed |

If Gate B keeps the as-approved chart gray instead of `bar-lo`, a second row enters this
table (line-token bars at 1.21:1; costs: the chart's meaning is invisible at low vision
and near-invisible to everyone in light mode). The recommended spec is `bar-lo`, under
which no break exists. §10, §15, §16, and TRANSLATE row 5 are untouched.

## 20. Build notes — prototype-discovered corrections (bind on the build)

1. Stat value row: the unit `<small>` must not sit on flex-baseline — it inflates the
   32px line to 37px (T4). Fix: `align-items:flex-end` or baseline-shift on the small.
2. Pill inside a `<dl>` row: line-box overhang cascades 1.5px — set the pill's container
   `line-height` explicitly (T4).
3. Panel width arithmetic: 03's stated 512px is really 514px — the th checkbox column is
   16px, not 14 (T4). Comps' region sums amended by +2.
4. Sparkline: `vector-effect: non-scaling-stroke` required (non-uniform 76×22/80×24
   scale); data padded to y∈[2,22], x∈[1,79] so the pinned stroke never clips (T2).
5. Stat label row: `min-height: 22px` pins the row with and without a sparkline (T2).
6. Panel head: line-height pinned 16px for deterministic baselines (T3).
7. Bar chart sparse state (≤2 months): cap bar-group `max-width` (T3's one-liner) or
   2-month charts render 132px slabs.
8. Skeleton loading stat cards: flex-column, not margin-stacked — margin collapse made
   loading cards 108px vs loaded 114px before the fix (T2).
9. Palette query input: opaque card fill (constraint §6); palette hint text ink, not ink2.
10. Re-measure table row heights when JBM Variable is vendored (±2px expected, T5).

## 21. Deferred decisions (§16 table)

| decision needed | if deferred, what happens |
|---|---|
| Chart gray: `bar-lo` (recommended) vs as-approved line-gray — **decide AT Gate B** | Deferred past the gate, the chart ships either failing 3:1 or silently changed from the approved board — both are the bad version of this choice |
| Low-end Windows iGPU glass measurement (fleet hardware) | The T1 fleet claim stays PARTIAL; the opaque floor is built, so the cost of being wrong is a settings default, not a redesign — but nobody learns the real number until build QA on a fleet machine |
| JBM vendoring + subset weigh-in | Mono metrics stay ±2px approximate and the tier-1 font line stays INFERRED; contingency (tier-2 + swap) is pre-decided so the failure mode is a flash of SF Mono, not a broken budget |
| Operator interview (TOOLS §1's three questions, never asked) | §13.1's counts stay estimates; if the real day differs, density and keyboard priorities shift and the cost lands at Loop 4 as re-prioritization |
| DPR-2 sparkline/hairline crispness | Stays INFERRED (vector by construction) until one retina capture exists |
| Three-question re-run with real data | Owed at Loop 4 per CRAFT.md — techniques that survived empty layouts must survive words and rows |
| Column choice/order/width per operator (TOOLS §6) | Operators live with the default column set until a later module pass; recorded, not silent |

## 22. Handoff clause

The goal is not *inspired by* this direction; it is **faithful to it**. During the build:
do not simplify into default templates; do not replace a distinctive surface with a generic
row; do not compress the stated spacing; do not flatten the type hierarchy; do not merge
surfaces into a repeating pattern that was not in the design; do not reintroduce nested
boxes the design removed. The five signature moves — mono-caps rhythm, the ink button,
sparklines, the two-layer shadow, the one glass moment — are never-cut (RISK 1). Where the
design is genuinely ambiguous, preserve the visible design language first, then the
spacing logic, then the component family — and ask before filling ambiguity with a
default. Values live in `tokens.json`; parse them, do not transcribe them.

## 23–25. Honest residue

**23. Where numbers came from:** every ratio in this file is script-computed or
PNG-sampled; every fps and px is from a named machine at a named viewport; the only
surviving estimates are labeled INFERRED (JBM subset size, mid-range fleet fps, DPR-2
crispness) or ESTIMATED (§13.1 counts).

**24. Rows still at prose resolution, named:** §13.1 (counts are estimates, not
observations); popover anatomy other than the ⌘K palette (declared level-2 + overlay
tokens, but no popover comp exists); the modal dialog's own comp (states + scrim + focus
rules are specified; its layout is inherited from panel spec, not drawn); title-identifier
optical matching (20px-in-28px stated, not yet rendered with real JBM).

**25. Gaps found in Loop 1's half while completing this file** (findings, not chores):
no re-reads of Loop 1 corpus files were needed — but four schema rows had no Loop 1
answer and were authored here from the approved artifacts: modes declaration (§2),
elevation levels (§14), icon source/licence (§14), and the TOOLS §13.1 day-per-role
(written from seed data because no operator interview was ever held — that absence is a
Loop 1/Gate A finding worth naming).
