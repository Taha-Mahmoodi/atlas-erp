# direction-draft.md — atlas-console, round 3 build-out (porcelain)

Working notes, Loop 1 conformance pass. Gate A is DECIDED (porcelain, 2026-08-14). This is not a
derivation — no concepts, no distinctness tests, no alternatives. PRINCIPLES §1–§3 suspended per
TRANSLATE.md's recorded escape-hatch decision. Faithful completion at full resolution.

## 0. What is fixed and where it came from

- Register: `gate-a-approved-porcelain.html`, `.po` / `.po.dark` blocks + the two comped frames
  (02 role home with ⌘K palette open; 03 items list). Refs 4 (Salung), 7 (Untitled UI),
  9 (TrustToken), 2 (glass sidebar), 6 (glass menu w/ keycaps) are the source register —
  all five inspected directly this pass.
- 02 and 03: match the approved executions. Refine only. 01/04/05/06/07 extend the register.
- Glass: floating layers ONLY (⌘K palette, popovers). Nothing structural blurs. Ever.
- One accent: #3f5bf6 light / #93a5ff dark. Everything else neutral. Status = tinted pills.

## 1. Read of the approved HTML — component inventory

Extracted at exact-value resolution into `design/porcelain/_register.md` §3–§4 (single source
for the seven workers; not duplicated here).

**Slip found in approved HTML:** `--ink3:#9becb0` (mint green labeled as a neutral, referenced
by zero rules inside `.po`). Dropped from the token set; logged. Not a design decision reversed —
a dead variable removed.

## 2. Contrast — VERIFIED this pass (script, not estimation)

Both prior rounds' estimated-only numbers were a named weakness; fixed. 38 pairs computed
(WCAG relative luminance, sRGB piecewise; OKLab per Ottosson for conversions; script kept at
scratchpad/contrast.py with assert self-checks). Result: **37/38 pass as approved. One failure,
one minimal adjustment:**

| Pair | Token | Before | After | Ratio |
|---|---|---|---|---|
| warn-tx on warn-bg (light) | warn-tx | `#96660f` | **`#94650c`** | 4.46 → **4.54** |

One 0.005 OKLCH L step, hue/chroma held. Dark mode needed nothing. Near-misses that PASSED and
are worth watching at Loop 2 render: acc on acc-t light **4.58**, warn′ pill **4.54**, ink2 on
bg light **4.81** — all pass, none with margin to burn if Loop 2 nudges any tint. Full table in
`design/porcelain/_register.md` §1 and DIRECTION.md §2.

## 3. Live-app content extraction (real fields, not invented)

Live scrape 2026-08-14 (headless browse, localhost:5173):

- **Login:** "Atlas ERP" / "Sign in to continue." / Company (tenant_slug, "acme") + Email +
  Password, all required / "Sign in". No links at all.
- **Vendor bill detail:** h1 = bill number; 6-field dl (Vendor · Status · Vendor's reference ·
  Bill date · Due date · Open amount); line table Account | Description | Net | Tax, account
  labels "2100 — GR/IR Clearing" (code — name), "—" for empty; footer Gross total; money
  "USD 54.00"; ONLY action = "Post bill" (Draft + finance.ap.manage only); statuses Draft /
  Posted / Partially paid / Paid / Reversed; **no document-flow links rendered today** although
  the backend records the chain (CLAUDE.md architecture rule 2) — 04 designs the promised chain
  and notes the gap.
- **New item form:** 11 flat fields, exact labels captured; "Create item"; live bug — visual *
  on Item code/Name but required semantics only on the selects; 05 fixes marker consistency.
- **Bad-ID behavior (the measured bug 07 replaces):** bill route → shell + "Loading…"
  **forever** (query error never handled); item route → **silently renders an empty Edit-item
  form with a live Save button**. Backend 422 (malformed) / 404 (missing); UI ignores both.
- Terminology lock confirmed conforming on every live screen. Formats: "USD 54.00",
  "Jun 20, 2026", em-dash as universal empty.

Pill mapping for bill statuses (decision): Draft=mute-dashed · Posted=ok · Partially paid=warn ·
Paid=ok (label distinguishes from Posted) · Reversed=bad.

## 4. Decisions taken in this pass (what the approved HTML doesn't answer)

1. **Monospace face named:** JetBrains Mono Variable, self-hosted, subset — mono-caps labels,
   identifiers, kbd chips. Approved HTML's `ui-monospace` stack becomes the fallback.
2. **44px floor vs approved 38px controls:** page-head controls keep 38px visual + 44px
   extended hit target (recorded); standalone primaries not in the approved frames (login
   submit, form save, empty/error CTAs) render 44px outright. Dense row-action clusters:
   WCAG 2.5.8 spacing exception ≥24px c-to-c. Compact density: rows ≥36px, controls ≥40px.
3. **h1 mapping:** 22px page title is the h1 everywhere; 04's h1 is the bill number.
4. **Focus ring:** 2px solid acc, 2px offset, :focus-visible — verified 4.86 light / 7.95 dark
   vs bg (floor 3.0).
5. **Glass a11y:** palette text ratios computed against worst-case composite (62% card over
   bg → #fcfcfc light / #18191e dark; 17.29 / 15.17) — labeled computed-not-rendered. Reduced
   motion: blur-in → instant fully-opaque panel, a designed state.
6. **ink3 dropped**; disabled = ink2 @55%, contrast-exempt, never the only signal.

## 5. Nine data states — where each lives

| State | Surface |
|---|---|
| loading | 02 (skeleton stats+panels), 03 (skeleton rows), 04 (bounded skeleton — never infinite) |
| true-empty | 06 (documented variant), 02's "Needs your action" empty line |
| filtered-empty | 06 (the surface: clear-filters action, count honesty) |
| sparse | 03 (8 of 214, honest pagination) |
| dense | 03 (forty-row note; compact mode) |
| error | 07 (bad-ID — the measured bug), 01 (bad credentials), 05 (validation), 07b (failed fetch) |
| permission-denied | 04 (Post bill gated; explanation line), 07c (403 route) |
| conflict | 04 (both versions, keep-mine/keep-theirs) |
| saving/in-flight | 05 ("Creating…", input preserved), 01 ("Signing in…"), 04 ("Posting…") |

## 6. ACCESS §13 — carried from rejected-v2/DIRECTION.md §3, deltas only

Rows 1,2,6,7,8,9,10,12,13,14,15,16,17,18,19 carry unchanged. Deltas for porcelain:
- Row 3: measured by script this pass, not estimated.
- Row 4: ring = #3f5bf6 / #93a5ff; glass check applies to the floating palette, not a bar.
- Row 5: no sticky glass bar exists; sticky table headers reserve space; glass layers are
  modal/floating, focus-trapped.
- Row 11: palette blur-in → instant opaque; skeleton shimmer → static.
- Rows 20–23: still N/A.

## 7. Dispatch state

- [x] contrast verified (one adjustment, logged above)
- [x] live content extracted
- [x] `design/porcelain/_register.md` written (workers' single source)
- [x] 7 surface-designer workers dispatched in parallel (01–07, each light+dark)
- [ ] collect worker returns → composition log → set-level check
- [ ] write DIRECTION.md (direction half) with composition log, SAFE/RISK, disclosure

## 8. Composition menu handed to workers

Anchors: centered-statement · dense-grid · stacked-center · left-rail-caption ·
right-rail-caption · split-pane. Backgrounds: flat-surface · soft-gradient · glass-layer ·
image. Expected porcelain outcome: 01/06/07 centered-statement, 02 left-rail-caption,
03 dense-grid, 04 right-rail-caption, 05 stacked-center — all flat-surface. Anti-repeat
criteria expected suspended (tool-shaped, no page-shaped subset), same carve-out both prior
rounds used; the never-vary list (palette/type/component family identical across surfaces)
checked for real.
