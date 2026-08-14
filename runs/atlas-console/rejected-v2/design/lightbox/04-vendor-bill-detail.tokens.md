# lightbox — Surface 4 of 7 — Vendor Bill Detail — composition sidecar

**Composition anchor:** `right-rail-caption`
**Background mode:** `flat-surface`

**Why:** the screen's real content is a wide line-items grid on the left with a narrower
document-flow chain as a detail/inspector rail on the right — the exact case the
`right-rail-caption` token names ("wide left field, narrow right rail: inspector, detail,
metadata"). `dense-grid` was considered and rejected: the grid alone isn't the majority of the
canvas here the way it would be on surface 03 (items list) — the document-flow rail is load-
bearing content, not subordinate chrome, so folding it into a single dense-grid anchor would have
undersold it. `flat-surface` is the only honest background-mode token for this concept's content
layer: no image, no gradient, no texture — one solid opaque substrate, which is the whole
structural argument of "lightbox" stated as a background choice rather than a decoration.

**Same tokens, both modes** — light and dark are one design in two palettes (per the concept's own
rule); the anchor and background mode don't change with theme, only the substrate/glass color
values do.

**Files:**
- `04-vendor-bill-detail-light.md`
- `04-vendor-bill-detail-dark.md`
