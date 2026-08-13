# the yard: Surface 5 of 7 — New Item Form
### Composition sidecar (read off disk for the set-level check, per `DIRECTION.md` §10)

| | |
|---|---|
| Concept | the yard |
| Surface | 05 of 07 — New Item Form |
| Platform mode | web/desktop-only (no native-mobile floors apply) |
| Aspect | fixed 1440×900 coded viewport |
| Composition anchor | **`stacked-center`** |
| Background mode | **`flat-surface`** |
| Comp files | `05-new-item-form-light.md`, `05-new-item-form-dark.md` |

## Why this anchor, against its neighbors

Surface 03 (items list) is `dense-grid` and surface 04 (vendor bill detail) is a document-
flow strip against a right-rail-caption split — both dense, both asymmetric. This screen is
told explicitly to read calmer than either. `stacked-center` does that structurally: one
column, no side rail of content competing for attention, generous held space left and right
of the form. `flat-surface` does the same for the substrate: no gradient, no texture, no
image — the form card is the only thing on the canvas that isn't the persistent left nav.

## State model (shared, palette-agnostic — binds both light and dark)

This is a behavior requirement the layout has to accommodate, not a color choice, so it
lives once here rather than duplicated in both palette files.

- **Field values persist in form state across a failed blur-validation and a failed submit.**
  A rejected `POST` re-renders the same field-level errors without clearing any input this
  is the direct fix for live-app defect #2 ("lose what the operator typed"). No field is
  ever reset by an error response.
- **Validation fires on blur, never on keystroke.** No per-character re-validation, no red
  border appearing while the operator is still typing.
- **Error messages are plain words next to the field, never the raw backend string.**
  "Field required," "Input should be a valid UUID" and similar FastAPI/Pydantic text never
  reaches the screen; each field's message is authored copy translated from the failure
  category (required / format / uniqueness / reference-not-found).
- **Each field's error slot is a `role="status"` (implicitly `aria-live="polite"`) region,
  empty until populated.** Advisory, not imperative — per the access notes, this is not an
  `alert`/assertive interruption, because nothing crashed and nothing was lost. Screen
  reader users hear the message once it lands on blur, without a modal-style interruption.
- **The field-level error visual reuses the concept's own atomic unit**, not a plain red
  underline: a small rounded error-hue token (the Overdue/Error glyph, shrunk to inline
  scale) sits before the error text, shape + hue together — the same signal-token mechanism
  used everywhere else in the concept, applied down to form-validation scale. This is the
  collision doing real work on this screen, not just the record-status columns.

## Inline vendor-create (never abandon the form)

- The Vendor field is a combobox. Typing filters existing vendors live.
- When the query has no match, the results list's last row is a pinned, visually distinct
  option: **"+ Create vendor '<query>'"** (accent-tint fill, accent-ink "+" icon token).
- Selecting it expands an inline sub-panel **directly under the Vendor field, inline in the
  same card, same page** — never a modal, never a route change. The sub-panel holds one
  field (vendor name, pre-filled from the query, editable) and a 44px "Add vendor" /
  "Cancel" pair.
- On confirm, the sub-panel collapses and the combobox shows the new vendor selected, with a
  small neutral "new" chip beside it acknowledging it was just created inline rather than
  looked up.
- This directly answers the brief: the operator is never forced to leave the New Item form
  to go create a vendor record elsewhere.

## Sensible defaults

| Field | Default | Why |
|---|---|---|
| Quantity | `0` | new items start with no stock on hand until received |
| Reorder point | `0` | inert until the operator sets a real threshold; never left blank/undefined |
| Warehouse | operator's default warehouse, pre-selected, still changeable | most items get received into the same warehouse most of the time |
| Item name, SKU | none | identity fields, no safe guess to default to |
| Vendor | none, field left empty | optional; forcing a guess here would misattribute sourcing |

## Enter submits

Native `<form>` submit-on-Enter behavior is sufficient — no custom keydown handler needed
for plain text/number fields (ladder: native platform feature covers it). The one carve-out:
the Vendor combobox's open suggestion listbox must consume Enter to select the highlighted
option, per standard ARIA combobox pattern, not fall through to form submit while a
suggestion list is open. That's existing combobox behavior, not a bespoke rule for this
screen.

## Primary button label

**"Create item."** Never "Save" — the brief is explicit that the button names the action it
performs, and "Save" is ambiguous about whether a new record is created or an existing one
is edited. This is a brand-new record every time this screen is reached.

## Terminology lock, confirmed applied

item (not product/sku) · vendor (not supplier) · warehouse (not location) — checked against
every label on this screen: "Item name," "SKU," "Quantity," "Reorder point," "Warehouse,"
"Vendor." No violating term appears anywhere in either palette file.

## Self-check before return (embarrassment gate)

- Palette hexes — re-read both palette tables in the light/dark files against the values
  given in the dispatch brief and `DIRECTION.md` §6: match, no transcription drift found.
- Body-size type (14px/450) legible at the stated weight; 12px error text is the smallest
  element on the screen, flagged as the tightest legibility case, not hidden.
- No mobile safe-area bands apply — this is a fixed desktop viewport, no platform-mode
  floors beyond the stated 44px control floor, which is honored on every interactive
  element.
- Collision readable: bento card-as-form-container, signal-token reused at inline-error
  scale, categorical lane hue on the active rail item — not a Bento skin over a generic form.
- Composition differs from neighbors 03/04 per the "why this anchor" note above.
- No garbled text, no invented logo, no hollow superlative, no fabricated data — the only
  invented string is the placeholder SKU pattern, plausible-length, domain-appropriate.
- Both menu tokens above describe what the spec actually states, not what would score better
  on the set-level check.
