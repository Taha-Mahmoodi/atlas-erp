# lightbox: Surface 5 of 7 — New Item Form — composition sidecar

**Composition anchor:** `stacked-center`
**Background mode:** `flat-surface`

Applies identically to both mode files below — the anchor and background mode are structural
(layout, not palette), and this concept's structure does not change between light and dark.

- Light spec: `05-new-item-form-light.md`
- Dark spec: `05-new-item-form-dark.md`

## Why these two tokens

`stacked-center` — one 640px vertical run of fields down the center of the 1200px main-content
field, space held either side (`x520–1160` inside a `x240–1440` content area). This is the
deliberately calmer surface in the set: surfaces 03 and 04 either side of it are dense
`role="grid"` tables reaching for `dense-grid`/`left-rail-caption`-shaped compositions; a form
that only asks the operator to fill six fields in sequence gets a single reading column instead,
which is also the layout that makes a per-field, blur-triggered error model legible — one thing
at a time, top to bottom.

`flat-surface` — one solid `substrate` fill behind everything except the one permitted glass
object (the command bar, persistent chrome, not this screen's subject). No image, no gradient,
no texture on the content layer, which is the concept's collision stated as a background-mode
token rather than restated in prose: the data layer is opaque by construction, and a form is
content, so it inherits `flat-surface` exactly as the tables and the record-detail screens do.
The one place this screen could have quietly broken the concept's own rule — the Vendor
combobox's popup listbox — is called out explicitly in both mode files as *also* `flat-surface`
(substrate fill, hairline border, no blur), because an app-owned popover is the single likeliest
spot for glass to leak onto a second object by accident.
