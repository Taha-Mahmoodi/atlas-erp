# DESIGN.md — Atlas ERP visual system

Fiori-inspired enterprise product UI. Mood: *harbor logistics office at 08:00 — ledger paper,
signal blue, everything labeled.* Color strategy: **Restrained** — neutral surfaces, one cobalt
accent carrying actions/selection, semantic colors reserved for state.

## Color (OKLCH, defined as Tailwind v4 `@theme` tokens in `frontend/src/styles.css`)

| Token | Value | Use |
|---|---|---|
| `--color-canvas` | `oklch(0.98 0.003 260)` | App background |
| `--color-surface` | `oklch(1 0 0)` | Cards, tables, panels |
| `--color-panel` | `oklch(0.955 0.005 260)` | Sidebars, toolbars (second neutral layer, cool) |
| `--color-ink` | `oklch(0.22 0.02 260)` | Body text |
| `--color-ink-muted` | `oklch(0.45 0.015 260)` | Secondary text, labels (AA on canvas/surface) |
| `--color-ink-faint` | `oklch(0.60 0.01 260)` | Disabled, placeholders-adjacent metadata |
| `--color-line` | `oklch(0.90 0.006 260)` | Borders, dividers |
| `--color-primary` | `oklch(0.45 0.15 260)` | Actions, selection, focus, links (brand seed) |
| `--color-primary-strong` | `oklch(0.38 0.15 260)` | Hover/active on primary |
| `--color-primary-tint` | `oklch(0.94 0.03 260)` | Selected rows, active nav, info chips |
| `--color-success` | `oklch(0.50 0.12 150)` | Posted / matched / passed |
| `--color-success-tint` | `oklch(0.95 0.03 150)` | Success chip bg |
| `--color-warn` | `oklch(0.55 0.12 75)` | Draft pending / tolerance edge |
| `--color-warn-tint` | `oklch(0.96 0.04 85)` | Warning chip bg |
| `--color-danger` | `oklch(0.50 0.18 25)` | Exceptions, destructive actions |
| `--color-danger-tint` | `oklch(0.95 0.03 25)` | Danger chip bg |

Light theme only in v1 (office ambient light, correctness-critical reading). Dark theme is a
token swap later — components must only use tokens.

## Typography

- One family: `Inter, system-ui, sans-serif` — weights 400/500/600. No display font.
- Fixed rem scale, ratio ~1.2: 12 (meta/labels), 13 (table data), 14 (body/controls), 16
  (section titles), 20 (page titles), 24 (KPI values). Tabular numerals (`font-variant-numeric:
  tabular-nums`) on all money/quantity cells.
- Uppercase reserved for column headers and status chips at 11–12px with 0.02em tracking.

## Spacing & layout

- 4px base grid. Table cell padding: 8×12 compact, 10×16 regular.
- Structural responsiveness (collapse sidebar, stack form columns) — no fluid type.
- Radius: 6px controls/chips, 8px cards. Shadows: one level only
  (`0 1px 2px oklch(0 0 0 / 0.05)`); elevation is for menus/dialogs, not decoration.

## Motion

State feedback only, 150ms ease-out on hover/focus/selection; skeleton shimmer for loading.
No entrance choreography. `prefers-reduced-motion`: transitions drop to instant.

## Components (src/components/ — ERP-agnostic, data+callbacks only)

- **DataGrid** — the workhorse. Sortable headers (`aria-sort`), sticky header row, compact
  density default, skeleton loading rows, teaching empty state, keyset "load more", row
  hover/selection, right-aligned numeric columns.
- **FormBuilder** — field-definition-driven forms: text/number/date/select/checkbox/textarea,
  1–2 column layout, inline errors (`aria-invalid` + described-by), busy submit.
- **Kanban** — columns of cards, HTML5 drag between columns plus keyboard move menu; used by CRM
  pipeline and any staged flow.
- **KpiCard** — dashboard tile: label, value, delta with direction+goodness, loading skeleton,
  optional drill-through click.
- **DocFlowViewer** — the document-flow chain (D-012): nodes leveled left→right from roots,
  status-chipped nodes, edge labels (link types), current-node highlight, node click.

Interaction affordances are uniform: focus ring `2px` primary at 2px offset; disabled = 45%
opacity + `cursor-not-allowed`; destructive actions always danger-colored and never adjacent to
primary actions.
