# the yard: Surface 4 of 7 — Vendor Bill Detail — composition sidecar

Read off disk by the set-level check (`DIRECTION.md` §10), not out of any return message.

- **Composition anchor:** `right-rail-caption`
- **Background mode:** `flat-surface`
- **Surface:** desktop/web-only, no platform mode (`DIRECTION.md` §2) — the four mobile safe-area
  bands don't apply. The equivalent desktop obligation (`ACCESS.md` §13 row 5, this concept: sticky
  chrome reserves real space, never floats) is honored via the `space-sticky = 56px` token, reused
  for the global top bar and reserved (not actively needed) on the line-items grid's header row.
- **One line:** wide left record-card against a narrow right-rail flow-strip — the concept's own
  stated shape for record detail ("a record detail opens as a right-side panel holding the
  document-flow chain"), and the one surface in this 7-comp set built around a persistent inspector
  rail rather than a dense grid (surface 3) or a bento grid proper (surface 2).
- **What this comp decided beyond the dispatch:** fixed the confirmed no-breadcrumb/no-back-nav
  defect with a real `nav aria-label="Breadcrumb"` as the first element inside `<main>`; rendered
  the PO→GRN→Bill chain as three rows on one connector inside a single flow-strip card (not three
  nested cards) to keep the screen's card count at exactly two, matching Bento's "card size states
  importance" rule literally; gave every checked-by person an avatar-chip (initials, no photo,
  `§14`) per the concept's own avatar-chip rule for person-attached records; sized the Approve
  button's label at 16px/600 per `ACCESS.md` §13 row 3's explicit instruction for the accent-
  emphasis fill, and left it disabled on this specific record since the real seed data's status is
  already POSTED (Void stays enabled — a posted bill can still be voided); put the Void
  confirmation modal's initial focus on Cancel, per the dispatch instruction, stated explicitly
  rather than left to be inferred at build time.
- **Not satisfied:** the avatar-chip name/department wrap inside a 256px column is budgeted (256px,
  12px/16px) but not resolved to the character — a build-time line-wrap question, not a withheld
  design decision. See both spec files' final section.

## Files in this comp

- `04-vendor-bill-detail-light.md` — full spec (layout, type, palette, flow-strip, modal, content
  direction, self-check)
- `04-vendor-bill-detail-dark.md` — palette/token delta against the light file; layout is shared
  and stated once, in the light file
- `04-vendor-bill-detail.tokens.md` — this file
