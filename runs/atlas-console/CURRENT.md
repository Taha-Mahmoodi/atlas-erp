# CURRENT.md — atlas-console

Measured, not adjudicated. Extracted from the live app at `http://localhost:5173`, logged in
as `owner@acme.test` / tenant `acme`, production-style build (single hashed JS/CSS bundle, not
Vite's unbundled dev-server output). Screenshots in `shots/current/`. Nothing below is a defect
until `STYLES.md` positioning (in `SCOUT.md`) says what it is a defect *against*.

---

## 1. Fonts actually in use

One family, everywhere sampled (login, dashboard, every list, every form, the kanban board):

```
"Inter Variable", Inter, system-ui, sans-serif
```

Self-hosted: `assets/inter-latin-wght-normal-*.woff2`, 48,256 bytes, served from the app's own
origin, not a Google Fonts CDN link. Matches `TRANSLATE.md` row 6 exactly
(`@fontsource-variable/inter`). No second family found on any sampled page — no monospace for
identifiers/codes (`BILL-2026-00003`, `ITM-BOLT` all render in Inter), no serif anywhere.

## 2. The real palette, ranked by occurrence

Sampled on the dashboard (highest-traffic screen). All values are **OKLCH**, not hex — every
color on every page sampled is an OKLCH token, no raw hex or named CSS colors found in computed
styles anywhere in the app.

| Value | Count | Read |
|---|---|---|
| `oklch(0.22 0.02 260)` | 95 | primary text/ink |
| `oklch(0.45 0.015 260)` | 35 | secondary text |
| `oklch(1 0 0)` | 21 | card/surface white |
| `oklch(0.9 0.006 260)` | 20 | hairline border |
| `oklch(0.45 0.15 260)` | 13 | accent (links, active nav, primary buttons, focus ring) |
| `oklch(0.94 0.03 260)` | 13 | accent-tint chip background (active nav, some badges) |
| `rgb(0, 0, 0)` | 7 | **noise** — traced to `<html>`, `<head>`, `<meta>`, `<title>`; browser-default `color` on non-rendering elements, paints nothing. Excluded from the read below |
| `oklch(0.6 0.01 260)` | 3 | muted label text |
| `oklch(0.98 0.003 260)` | 2 | page background |
| `oklch(0.955 0.005 260)` | 1 | neutral badge background ("CLOSED" in Sales) |

Additional tokens sampled off other screens (status badges, login error, form validation):

| Value | Where seen |
|---|---|
| `oklch(0.5 0.18 25)` | login error text, red/error |
| `oklch(0.95 0.03 150)` | green badge bg (ACTIVE, RECEIVED, and — see §7 — also CLOSED in Procurement) |
| `oklch(0.5 0.12 150)` | green badge text |
| `oklch(0.96 0.04 85)` | amber badge bg (PARTIALLY_DELIVERED) |
| `oklch(0.55 0.12 75)` | amber badge text |

**The neutral ramp is hue-locked to the accent.** Every neutral above — text, border, background —
carries `260°` hue at chroma between `0.003` and `0.02`. That is not an accident of sampling: it
is the exact "tinted neutral" construction `STYLES.md` names (accent hue held constant, chroma
0.005–0.03, lightness carries the ramp). The accent itself (`oklch(0.45 0.15 260)`) and every
neutral share the same 260° hue angle at different chroma. Worth flagging precisely because this
is a level of construction that does not happen by accident or by Tailwind defaults — Tailwind's
own gray scale is not hue-locked to a project's accent out of the box.

## 3. The heading scale, as rendered

Sampled across 8 pages (dashboard, inventory list, finance list, vendor-bill detail, HR list,
manufacturing list, reporting dashboard, item form): **one heading level in productive use,
everywhere.**

| Page | Tag | Text | Size | Weight |
|---|---|---|---|---|
| every page sampled | H1 | page title | `20px` | `600` |
| Home dashboard only | H2 | "MODULES" (section eyebrow) | `12px` | `600` |

No H3–H6 found anywhere in the pages sampled. The H1 is 20px/600 with total consistency across
11 modules and every screen shape (list, form, detail, kanban, dashboard) — the same size and
weight on every single page title with no observed exception. The H2 is smaller than the H1 (12px
vs 20px), used once, as an all-caps section label, not as a second content level. There is no
ratio-derived or role-indexed scale beyond these two sizes — this is a flat, two-step hierarchy,
not a scale with drift in it.

## 4. Interactive elements under the target floor

Raw sweep (`a,button,input,select,textarea,[role=button],[tabindex]`) on the dashboard returned
33 elements; all 33 were visibly rendered (`display` not `none`, non-zero box) — no closed-menu
or `tabindex="-1"` noise on this screen. Cleaned counts by screen:

**Login** (4 elements): 3 inputs at 318×34, 1 submit button at 77×32. Vertical gaps between
fields: 36px. **Adjudication (`SURFACES.md` §2):** cross-platform-neutral preferred pair is
48dp/44pt; these undershoot it. WCAG 2.5.8's 24×24 CSS px is cleared on size alone (318×34,
77×32 both exceed 24×24) — no spacing exception even needed. Net catch, not a law violation.

**Sidebar nav** (13 links, every module): each exactly 223×36, stacked with **zero gap** between
adjacent items (y-positions increment by exactly 36px). Undershoots the 40dp Material
pointer-target row (24dp icon / 40dp target) and the 44pt cross-platform pair. Clears WCAG
2.5.8 on size alone (223×36 » 24×24). This is uniform across every nav item, not an outlier.

**Header "Sign out"** (78×32): same read as above — clears WCAG on size, undershoots the 40/44
pointer-target preference.

**Table rows** (inventory items, vendor bills, etc.): row height 33–37px, consistently. Same
undershoot-but-clears-WCAG read.

**KPI cards, module cards** (dashboard): 218×108 and 276×88 — far above every floor in
`SURFACES.md`, no finding.

**Net read:** every control that undershoots the 40/44/48 preferred pointer-target numbers does
so by the same margin (~32–37px against a 40–48px target), everywhere it was sampled, and every
one of them clears WCAG 2.5.8 on size alone. This reads as one consistent density decision, not
scattered undersized controls — noted here as a measurement, with the choice-vs-accident question
carried to `SCOUT.md`.

## 5. The two-tier performance read

**Shell weight** (initial load, dashboard): JS 232,065B (one hashed bundle), CSS 6,499B, font
48,256B self-hosted woff2. No images, no icon-font, no third-party script observed on the
network log. `POST /auth/login`, `GET /auth/me`, `GET /reporting/dashboard` are the only API
calls before first paint.

**LCP path:** `first-paint` / `first-contentful-paint` both at 40ms; the LCP candidate is a
`<span>` (5,952px² box, likely a KPI figure), not an image — nothing heavy sits in the critical
path.

**This number is not load-bearing.** It was read on `localhost` against a pre-built bundle with
zero network latency, zero TLS handshake, zero CDN. It says the shell *can* be light (small
bundle, no render-blocking media) but says nothing about real-world LCP on a deployed instance.
Flagged in full under Limits in `SCOUT.md`.

## 6. Console and error behavior observed during extraction

- Clean console (no errors, no warnings) across normal navigation: home → list → form → detail →
  kanban.
- `401`s appear only from a deliberately-wrong login attempt made during extraction (expected).
- `422`s appear only from deliberately-submitted invalid data (empty required fields, a
  malformed item ID) made during extraction (expected) — see absence sweep §8 for what the UI
  does with that response.
- No `ErrorBoundary` exists anywhere in the source tree (`grep -rli errorboundary` returned
  nothing; `App.tsx` is a bare `QueryClientProvider` wrapper with nothing else). An unexpected
  render error anywhere in the tree has no designed fallback — this is a structural fact read
  from source, not observed live (no render error was actually triggered).

## 7. Status vocabulary, as rendered (cuts across "positioning" and "absence" both)

Sampled badge colors for the same status word across modules:

| Status word | Module | Background | Text |
|---|---|---|---|
| `CLOSED` | Sales (orders) | `oklch(0.955 0.005 260)` (neutral gray) | `oklch(0.45 0.015 260)` |
| `CLOSED` | Procurement (purchase orders) | `oklch(0.95 0.03 150)` (green) | `oklch(0.5 0.12 150)` |
| `RECEIVED` | Procurement (purchase orders) | `oklch(0.95 0.03 150)` (green) | `oklch(0.5 0.12 150)` |

The same word (`CLOSED`) renders in two different colors depending on which module's list it
appears in, and two different words (`RECEIVED`, `CLOSED`) render in the *same* color within one
module's own list. `NEW` (CRM leads) and `SUBMITTED` (HR leave requests) — two different words,
two different modules — happen to share the exact same accent-blue chip. Measured as-is; carried
to `SCOUT.md`'s positioning read as evidence, not flagged as a "defect" here.

## 8. The absence sweep

### Nine data states (`TOOLS.md` §4) — reached deliberately where possible

| State | Reached how | What renders |
|---|---|---|
| **Empty (true)** | Navigated to modules with no seed rows: `inventory/stock-counts`, `manufacturing/mrp/runs` | Plain text inside the table area: `"No stock counts yet."` / `"No MRP runs yet."` Same wording pattern every time (`"No {noun} yet."`). No explanation of what the screen is, no first-action guidance in the empty-state text itself (a "New X" button exists in the page header regardless of row count, not inside the empty state) |
| **Empty (after filter)** | Filtered inventory items list to `NON_STOCKED` (zero matches) | **Identical** message and layout to true-empty: `"No items yet."` No distinction from the true-empty state, no "clear filters" affordance |
| **Loading** | Not reliably forceable on localhost (all responses return in single-digit-to-tens of ms). Not reached |
| **Partial** | Not reached — no multi-widget screen was found where one data source could be made to fail independently of the others without backend access |
| **Error** | Navigated to `/inventory/items/nonexistent-id-999` (malformed ID, backend returns `422`) | **No error state renders at all.** The page silently shows "Edit item" with every field blank — indistinguishable from a form that reset, not from a record that wasn't found. The `422` is visible only in the browser console, never surfaced to the user |
| **Permission denied** | Not reached — single-role demo tenant (`owner`), no second role available to test a denied action against |
| **Offline / degraded** | Not reached — no offline simulation available through the extraction tooling used, and no `navigator.onLine` or offline-handling code found in source (`grep` for "offline" across `frontend/src` returned nothing) |
| **Stale** | Not reached live. Source grep for "stale" found only developer comments about cache TTL and snapshot timing — no user-facing "fetched at X, refresh?" UI exists |
| **Conflict** | Not reached — would require two concurrent sessions editing the same record; out of scope for a single-session extraction pass |
| **Bulk** | Not reached — no bulk-action UI (multi-select + batch operation) was found on any list screen sampled |

### Structural omissions

| Omission | Status |
|---|---|
| Custom 404 | **Absent.** Unmatched routes fall through to the catch-all `$moduleKey` route, which renders `"Unknown module."` as bare text inside the shell chrome — no heading, no explanation, no link home. Better than a blank screen or a stack trace; not a designed not-found state |
| Skip-to-content link | **Absent.** No match for "skip" in any rendered page or in source |
| Back navigation out of a flow | **Absent** on the one flow tested: opening a vendor bill detail page (`/finance/vendor-bills/{id}`) provides no breadcrumb and no back link — only the sidebar (which returns to the module home, not the list) or the browser's own back button |
| Form validation | **Present, but not per `TOOLS.md` §5.** See §9 below — validation exists, is real, but is not field-level |
| Legal links (privacy/terms) | **Absent.** No match in source or rendered pages. Plausibly N/A for an authenticated internal tool with no public-facing surface — noted, not weighted |
| Cookie consent | **Absent.** Only source match for "cookie" is the `HttpOnly` auth-cookie comment in `AuthGate.tsx`, unrelated to consent. Plausibly N/A for the same reason as legal links |
| Global / cross-entity search | **Absent.** No search input exists on any sampled screen. `TOOLS.md` §7 asks for search that spans entities once a system is this size; the router alone lists 150+ routes |
| Command palette / "go to" shortcut | **Absent.** `Cmd+K` produces no response (no dialog, no visible change) |
| Dark mode | **Absent.** No theme toggle found, no `prefers-color-scheme` handling observed |

## 9. Form validation, as rendered

Submitting the "New item" form empty produced a single alert block at the **top of the form**,
concatenating raw backend validation strings verbatim:

> Field required; Input should be a valid UUID, invalid length: expected length 32 for simple
> format, found 0; Input should be a valid UUID, invalid length: expected length 32 for simple
> format, found 0

This is the Pydantic/FastAPI validation error text passed through unmodified — not rewritten
copy, not per-field placement, not triggered on blur. Individual fields show no local error
state (no red border, no inline message) even though the alert names specific fields.

## 10. Resize behavior (`STYLES.md` "reveal, don't stretch" / `SURFACES.md` §5)

Same dashboard screenshotted at 1440, 1024, 768, and 390 CSS px width (`shots/current/dashboard*.png`):

- **1440 → 1024 → 768:** the KPI card grid and module-card grid reflow (5-across → 3-across →
  2-across). The sidebar nav stays a fixed ~223px-wide, always-expanded column at every one of
  these widths — no icon-only collapse, no width change, no reveal/hide behavior of any kind.
- **390 (phone width):** the sidebar nav is still the same fixed ~223px column, now consuming
  more than half the viewport. Content is visibly clipped on the right: KPI figures cut off
  mid-digit (`USD 237,4|`), "Sign out" wraps and truncates. This is the desktop layout compressed
  into a narrow viewport, not a narrow-width design — there is no breakpoint logic in the shell at
  all (confirmed against `frontend/src/shell/AppShell.tsx`: no responsive class variants on the
  nav container).

Whether phone-width support is in scope for this surface is unanswered by the DOM — `TRANSLATE.md`
row 2 (viewer and task) is still `TODO`. Reported as a measured fact, not a defect, until that row
is filled.

## 11. Screenshot inventory

All in `runs/atlas-console/shots/current/`:

`login.png` · `dashboard.png` (1440) · `dashboard-1024.png` · `dashboard-768.png` ·
`dashboard-390.png` · `list-inventory.png` · `list-inventory-filtered-empty.png` ·
`list-finance-accounts.png` · `list-vendor-bills.png` · `detail-vendor-bill.png` ·
`form-item.png` (new-item, blank) · `form-item-validation.png` (submit-time error alert) ·
`error-bad-id.png` (silent-failure edit form for a nonexistent record) · `404.png`
(catch-all "Unknown module.") · `focus-state.png` (keyboard focus ring) · `crm-kanban.png`
(Pipeline board, a structurally different view type from every list/form/detail page above).
