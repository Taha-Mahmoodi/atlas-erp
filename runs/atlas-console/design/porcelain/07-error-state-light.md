# porcelain — 07 Error state — light — 1440×900

Anchor: **centered-statement** · Background: **flat-surface** (register §6 closed menus).
Full §3 shell — the 248px sidebar stays fully operable: the error boundary is scoped to the
route outlet, never the shell. An error in one route never takes down navigation.
Neighbor line: 06 (empty) invites and points forward; 07 apologizes and routes back — no
invitation language, no illustration, no mascot, no red banner.

**What this replaces (measured, `shots/current/error-bad-id.png` + live inspection):**
a vendor-bill route with a bad id renders the shell with "Loading…" forever — the query
error is never handled. Worse, a bad *item* id silently renders the full "Edit item" form
with every field empty and a live "Save changes" button, so a user could believe they are
editing a real blank record. Backend answers 422 (malformed id) or 404 (well-formed,
missing); the UI ignores both. In this design nothing is silently swallowed: **the
bad-item-id route renders THIS state, never an empty editable form.**

**422 and 404 collapse into this one user-facing state.** The distinction is logged
(console + telemetry with the raw status and id), never shown — no error codes in the
headline or anywhere on the surface, per the register's plain-sentence rule.

## Region map (x, y, w, h — sums checked in §9)

| Region | x | y | w | h |
|---|---|---|---|---|
| Canvas (bg) | 0 | 0 | 1440 | 900 |
| Sidebar (§3 shell, verbatim) | 0 | 0 | 248 | 900 |
| Main region | 248 | 0 | 1192 | 900 |
| Breadcrumb | 284 | 38 | 1120 | 16 |
| Statement block | 604 | 363 | 480 | 174 |
| — h1 | 604 | 363 | 480 | 28 |
| — sentence (2 lines) | 604 | 401 | 480 | 40 |
| — identifier echo | 604 | 453 | 480 | 16 |
| — actions row | 690 | 493 | 308 | 44 |

Statement block is centered both axes in the main region: x = 248 + (1192−480)/2 = 604;
y = (900−174)/2 = 363. Internal rhythm: h1 28 → gap 10 → sentence 40 → gap 12 → echo 16 →
gap 24 → actions 44. Text inside the block is center-aligned.

## Per-region spec

- **bg**: `#f7f7f8` edge to edge in the main region. No card behind the statement — the
  state sits directly on bg (flat-surface; a card would dress the apology up as content).
- **Sidebar**: §3 shell exactly as comped in surfaces 02/03 — 248×900, card `#ffffff`,
  1px line `#e9e9ee` right border, workspace switcher, section labels, nav rows, user card
  (Amira K., Buyer · Procurement) pinned bottom. This file changes nothing in it.
  **Finance** row active (acc-t `#edf0fe` fill, acc `#3f5bf6` text, 550) — the failed route
  lives under it; counts and all rows stay live and clickable.
- **Breadcrumb**: "Finance / Vendor bills / Not found" — 12px ink2 `#6b6d76`, current
  segment "Not found" ink `#17181c` /500. Route-aware: on the items route it reads
  "Inventory / Items / Not found".
- **h1**: "This record wasn't found." — §2 h1, Inter 22px/650, −0.01em, lh 28, ink. One
  line at 480px. `tabindex="-1"`; route-level error moves focus here. Document title
  updates to "Not found — Atlas ERP".
- **Sentence**: "Nothing was changed. The link may be stale, or the record may have been
  removed." — §2 body, 13px/450 lh 20, ink2. Wraps to 2 lines at 480px. No blame, no
  jargon, no codes.
- **Identifier echo**: `vendor-bills/9ec54efb-…` — §2 identifier role, JetBrains Mono
  11px/500, ink2, centered. A `<code>` element containing the **full** requested path +
  id; CSS middle-truncates to path + first 8 hex chars, so select-all/copy yields the
  whole thing. This is what a support conversation points at.
- **Statement container** (h1 + sentence + echo): `role="alert"`.
- **Actions row**: ink button "Back to vendor bills" 170×44 (r10, ink fill, 13px/550
  white — §3 standalone-primary: 44px outright) + 10px gap + chip button "Go to dashboard"
  128×44 (r10, card fill, 1px line border, 13px ink). Both are links (`<a>`) styled per
  §3 — this is navigation, not action. The ink button is **route-aware**: it names the
  list it returns to ("Back to items" → `/inventory/items` on the items route).
  **No "Try again" here** — retrying a not-found cannot help; retry exists only in
  variant (a), and the difference is deliberate.
- **Focus ring**: 2px solid acc `#3f5bf6`, 2px offset, `:focus-visible` only.
- **No bad-tx anywhere on this surface** — deliberate. Nothing failed to save and nothing
  is dangerous; red stays reserved for data-loss-adjacent states (failed save, conflict),
  which live in forms. The calm is the register.

## Content (real, no lorem)

Breadcrumb: Finance / Vendor bills / Not found · h1: "This record wasn't found." ·
Sentence: "Nothing was changed. The link may be stale, or the record may have been
removed." · Echo: `vendor-bills/9ec54efb-…` (full id in DOM) · Actions: "Back to vendor
bills" · "Go to dashboard".

## States owed (each a variant of the same block)

**(a) Failed fetch / network.** Same layout. h1: "Atlas couldn't reach the server." (one
line). Sentence, one line (h 20): "Your work is unchanged. Check your connection, then try
again." Echo kept. Actions: chip "Try again" 100×44 + 10px gap + chip "Go to dashboard"
128×44 → row 238×44 at x 725. Below actions: gap 12 + a reserved 16px retry-note row —
an `aria-live="polite"` region, empty until a retry fails, then "Still couldn't reach the
server." 12px/450 ink2. Block h 182, y = (900−182)/2 = 359. Document title: "Can't reach
server — Atlas ERP". **Distinct from not-found: retry helps here and cannot help there**,
which is why "Try again" appears only in this variant. "Try again" re-runs the same query
in place; no full reload, input elsewhere untouched.

**(b) Permission denied (403).** Same geometry as the base block (h 174, y 363). h1: "You
don't have access to this record." (one line). Sentence (2 lines): "Nothing was changed.
Ask your workspace admin if you need access to vendor bills." Echo kept. Single action:
ink button "Go to dashboard" 144×44 centered at x 772 — the parent list may be equally
forbidden, so the surface doesn't offer a route that could bounce straight back here.
Document title: "No access — Atlas ERP". No retry.

**(c) Session expired.** One line: an `aria-live="assertive"` region announces "Your
session expired. Sign in again to continue — you'll return to this page.", focus moves to
it, then the app routes to surface 01 (login) with the return path preserved
(`?next=/finance/vendor-bills/9ec54efb-…`); after sign-in the user lands back on the
requested route, which then resolves to content or to one of the states above.

**The rule this surface enforces:** every skeleton (§3) in the app resolves to content,
to the 06 empty state, or to one of these states — a skeleton has no forever branch.
"Loading…" as a terminal state ceases to exist.

## Type table (deltas from §2 only)

| Use | Spec | Delta |
|---|---|---|
| h1, body sentence, breadcrumb | per §2 | none |
| Identifier echo | JetBrains Mono 11px/500, ink2 | identifier role in ink2, centered |
| Button labels | Inter 13px/550 (ink) · 13px/450 (chip) | §3 button specs |
| Retry note (variant a) | Inter 12px/450 lh 16, ink2 | sub/meta role |

## Palette citation (pairs used only — §1 verified ratios)

| Pair | Ratio |
|---|---|
| ink on bg (h1, breadcrumb current) | 16.57 |
| ink2 on bg (sentence, echo, breadcrumb, retry note) | 4.81 |
| white on ink (ink button) | 17.74 |
| ink on card (chip label, sidebar) | 17.74 |
| ink2 on card (sidebar rows) | 5.15 |
| acc on acc-t (active nav row) | 4.58 |
| acc focus ring vs bg | 4.86 (floor 3.0) |
| line vs card 1.21 · vs bg 1.13 | decorative only, never sole signal |

## Accessibility

Skip link first in tab order, targets `#main-content` (shell present → bypass-blocks
applies). One `h1`, one `main`, one `nav aria-label="Primary"`. `role="alert"` on the
statement; SPA route-level error moves focus to the h1 (`tabindex="-1"`, §5); document
title per variant. Variant (a) polite live region for retry outcome; variant (c)
assertive + focus move (§5: session-expiry is assertive). Actions are links with their
destination in the name ("Back to vendor bills" — never bare "Back"); both 44px targets.
No color-only signaling — the state is carried by text; no timeout on this surface.
Sidebar remains fully keyboard-operable throughout.

## Self-check

Vertical: 363+28+10=401 ✓ · 401+40+12=453 ✓ · 453+16+24=493 ✓ · 493+44=537 = 363+174 ✓ ·
(900−174)/2=363 ✓. Horizontal: 248+1192=1440 ✓ · 604 = 248+(1192−480)/2 ✓ ·
690+170+10+128=998, 690−604=86=(480−308)/2 ✓. Variant (a): 28+10+20+12+16+24+44+12+16=182,
(900−182)/2=359 ✓; actions 100+10+128=238, 604+(480−238)/2=725 ✓. Variant (b):
(480−144)/2=168 → x 772 ✓. Breadcrumb 28+10=38 ✓ (§3 "10px below top"). All tokens and
ratios read back against `_register.md` §1–§5; anchor and background from §6's closed
menus.
