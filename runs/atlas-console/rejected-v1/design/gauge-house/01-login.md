# gauge-house: Surface 1 of 7 — Login

**Canvas:** 1440×900 fixed viewport, tool-shaped desktop, full chrome.
**Composition anchor:** `stacked-center`
**Background mode:** `textured-surface`

## Layout move

A single vertical run, centered on the canvas, held inside a title-block
frame — the same "as of" stamp language the rest of the concept uses, but
carrying no worklist. The calmest surface gets a blank field, not a
scaled-down dashboard.

```
0,0 ──────────────────────────────────────────────────────── 1440,0
│ STICKY HEADER — reserved, 0–48px, never overlapped         │ h=48
│ "GAUGE-HOUSE · ACCESS"(eyebrow, x=32)   "AS OF …"(x=1408,→)│
├──────────────────────────────────────────────────────────┤ y=48
│                                                              │
│                 CONTENT — y 48–900 (h=852)                  │
│              textured-surface: 24px blueprint grid,          │
│              1px lines oklch(0.92 0.006 58), low-contrast     │
│                                                              │
│           ┌──────────── 400px col, x 520–920 ─────────────┐ │
│           │  y=304 (centered: (852-341)/2 ≈ 256 top margin)│ │
│           │  TENANT eyebrow · 12/600 caps           h=16   │ │
│           │  +8                                             │ │
│           │  Acme  (org name) · 20/600              h=28   │ │
│           │  +16                                            │ │
│           │  ── hairline rule, 1px, full 400px ──   h=1    │ │
│           │  +16                                            │ │
│           │  [ERROR-STATE ONLY: alert banner, see below]   │ │
│           │  Email — label 12/450            h=16          │ │
│           │  +4                                             │ │
│           │  [ email field ─ 400×40, 1px hairline border,  │ │
│           │    2px radius, autofill/paste never blocked ]  │ │
│           │  +16                                            │ │
│           │  Password — label 12/450          h=16         │ │
│           │  +4                                             │ │
│           │  [ password field ─ 400×40, same border/radius,│ │
│           │    native show/hide, no custom masking overlay]│ │
│           │  +8                                             │ │
│           │  "— required, matched against tenant record"   │ │
│           │    meta 12/450, secondary-text, 1 line   h=16  │ │
│           │  +24                                            │ │
│           │  [ Sign in — button, 400×40, accent-emphasis   │ │
│           │    bg, white label 14/500, 2px radius ]  h=40  │ │
│           │  +16                                            │ │
│           │  "Need access? Contact your administrator."    │ │
│           │    meta 12/450, accent-ink, centered     h=16  │ │
│           │  y ends ≈ 645, bottom margin to 900 ≈ 255px    │ │
│           └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

Column height sums to 341px (85 title-block + 136 fields + 24 annotation +
40+16 button/footer gaps + 16 footer − rounding); centered in the 852px
content band gives ~256px above and ~255px below — a deliberately quiet,
symmetric hold, the honest read for four fields and a button rather than
forcing a dense-grid anchor onto content that doesn't have forty rows.

**Control floor check:** email field, password field, and submit button are
all 400×40 — meets the 40px floor for primary controls. Header is reserved
at 48px, distinct from and taller than the control floor, per the sticky-
chrome decision; content never draws under it.

### Error state (same surface, alternate state — not a second canvas)

On invalid-credentials submit, an alert banner inserts between the title-
block rule and the Email label, pushing the form down by its own height
(40px) + 16px gap (column re-centers; new total 397px, top margin ≈228px).
Banner: 400×40, background `oklch(0.95 0.03 25)` *(invented, modeled on the
accent-tint recipe — computed, not rendered)*, left-aligned 20×20 exclaim
glyph + text, reusing the concept's Error/Overdue status vocabulary (shape +
label, never color alone) rather than inventing a one-off alert style:

> **! CREDENTIAL CHECK FAILED — VALUES DO NOT MATCH RECORD.**
> `REF: AUTH-0913` *(right-aligned, mono-identifier style)*

Both fields' borders switch from hairline neutral to
`oklch(0.5 0.18 25)` at 1.5px on this state — a secondary reinforcement,
not the sole carrier of meaning (the banner's glyph + text already satisfy
that). No field is blocked from re-entry, paste, or autofill in this state
either.

## Type table

| Level | Face | Size | Weight | Line-height |
|---|---|---|---|---|
| screen title (org name "Acme") | Inter Variable | 20px | 600 | 28px (1.4) |
| section-eyebrow ("TENANT", header label) | Inter Variable | 12px caps | 600 | 16px (1.33), +0.04em tracking |
| body/data (field values, button label) | Inter Variable, tabular-nums | 14px | 450 (button: 500) | 20px (1.43) |
| meta (field labels, annotation, footer) | Inter Variable | 12px | 450 | 16px (1.33) |
| mono-identifier (`REF: AUTH-0913`) | IBM Plex Mono Variable | 13px | 500 | 18px (1.38) |

Line-heights are this comp's own layout decision — the dispatch's role-
indexed scale specifies size/weight only.

## Paired colors, at used size

| Pair | Where used | Ratio |
|---|---|---|
| primary text `oklch(0.20 0.01 58)` on substrate `oklch(0.985 0.003 58)` | field values, org name | 17.35:1 *(computed, not rendered)* |
| secondary text `oklch(0.45 0.012 58)` on substrate | labels, annotation, footer body | 7.14:1 *(computed, not rendered)* |
| accent-ink `oklch(0.42 0.09 58)` on substrate | "Contact your administrator" link-legal line | 8.71:1 *(given, dispatch palette)* |
| white on accent-emphasis `oklch(0.55 0.13 58)` | "Sign in" button label | 5.06:1 *(given, dispatch palette)* |
| error text `oklch(0.5 0.18 25)` on error-tint `oklch(0.95 0.03 25)` | error banner | 5.60:1 *(computed, not rendered — tint invented, modeled on accent-tint recipe since dispatch's STATUS block gives error text but not an error-chip background)* |
| hairline border `oklch(0.88 0.008 58)` on substrate | field borders, rule, header divider | 1.38:1 *(computed, not rendered — non-text; below the 3:1 WCAG 1.4.11 floor for required UI boundaries, see "couldn't satisfy" below)* |

Focus ring on both fields and the button: 2px solid accent-ink, 2px offset,
`:focus-visible` only, per the dispatch's global rule.

## Content direction

Login speaks in the same title-block register as the rest of the concept —
tenant name and "as of" timestamp stamped above the form — but withholds
the worklist and certificate strip entirely; the calmest surface in the set
earns a blank field, not a shrunk dashboard, and its one moment of concept
voice is the error banner borrowing the same status-chip vocabulary the
dense surfaces use for row state.

## Self-check (embarrassment gate)

Read back against the palette table above: all six pairs used on this
surface are accounted for, the two given ratios (5.06:1, 8.71:1) are
quoted verbatim from the dispatch rather than re-derived, and every value I
did derive is flagged computed/invented rather than presented as given.
Both control floors (40px fields/button, 48px reserved header) hold. Status
on the error state is shape+glyph+text, not color alone. No fabricated
brand name (tenant reads "Acme," the same placeholder already in the live
app's seed data, not invented for this comp). Would put a name on this.

## Couldn't fully satisfy

The hairline border color given in the dispatch palette
(`oklch(0.88 0.008 58)` on `oklch(0.985 0.003 58)` substrate) measures
~1.38:1 — well under the 3:1 WCAG 1.4.11 floor for a required UI boundary
like a field edge. This is an inherited palette constraint, not a choice
made on this surface; flagging it here since a login form's field
boundary is exactly the kind of component that floor is meant to cover.
Worth a Loop 1 palette check before this hairline value ships past Gate A.
