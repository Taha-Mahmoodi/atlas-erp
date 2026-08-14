# lightbox: Surface 1 of 7 — Login — composition sidecar

| Field | Value |
|---|---|
| Concept | lightbox |
| Surface | 01 of 07 — Login |
| Mode | coded comp (spec block) |
| Composition anchor | `centered-statement` |
| Background mode | `flat-surface` |
| Canvas | 1440×900 fixed, web/desktop-only |
| Platform mode | none (web/desktop-only surface) |
| Files | `01-login-light.md`, `01-login-dark.md` |

## What I decided

One flat substrate, one 360px form column dead-centered on the canvas (`centered-statement`),
zero glass — the concept's command bar doesn't exist before authentication, so this is the
concept's purest opaque instance: no card, no shadow, hierarchy from a 20px/600 h1 against
14px/450 body and 12px/450 meta labels, all on one `flat-surface`. The one decision beyond the
brief: the primary CTA uses the *verified* accent pairing (`accent-ink` light / `accent-dark`
dark) rather than the borderline `accent-emphasis` token, since the button label sits exactly at
the brief's own "don't use under 14px" floor and this is the one control on the screen a failed
click actually blocks. Dropped a signup/create-account link — Atlas ERP is admin-provisioned,
so that flow doesn't exist and adding it would be inventing product behavior.

## Constraints not fully satisfiable

- Two color pairs (white-on-accent-ink button fill for light, substrate-on-accent-dark button
  fill for dark) aren't stated verbatim in `DIRECTION.md` §7's tables — both are derived by
  symmetry with an adjacent stated pairing and flagged inline in both spec files per the
  document's own §11 disclosure (nothing in this run has been script-verified yet). Re-measure
  at Loop 2 build alongside the rest of the palette.
- No inline-validation error string is fully specified here (surface 07 owns the dedicated error
  register) — the light spec notes where it renders and what glyph grammar it borrows, not the
  exact copy.
