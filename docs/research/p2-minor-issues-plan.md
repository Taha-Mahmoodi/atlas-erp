# P2 — Minor Tracked Issues: Fix Plans

> **For agentic workers:** Each section is one self-contained fix — one branch, one PR, one issue
> closed, in any order. Steps use checkbox (`- [ ]`) syntax. Verified against the tree at
> 2026-08-15 (post-#191); re-verify line anchors before editing.

Five open issues, all `severity:minor`, all tracked. None blocks the hospitality work; #176's
`hospitality/models.py` interaction is noted in the Phase 20 plan (Task 3 splits the models file
*before* adding to it if the cap requires).

---

## #163 — Kanban leaks column totals into move-menu and aria-labels

**Root cause.** `KanbanColumn.title` is the *only* text field (`Kanban.tsx:13`), so
`OpportunityBoardPage.tsx:58-68` bakes the money total into it
(`"Prospecting · USD 60,000.00"`), and Kanban reuses it verbatim in the section
`aria-label` (`Kanban.tsx:53`) and the move menu (`:119` — "Move to Prospecting · USD
60,000.00"). The header (`:69`) is the only consumer that should see the total.

**Adjacent leak, fix in the same PR:** `Kanban.tsx:94` labels the card's move button
`Move ${key} to another column` where `key` is the raw opportunity UUID — screen readers get a
UUID read aloud. Add `itemLabel?: (item: T) => string` (fallback: the current key) and use it
there.

**Fix.** Add `headerExtra?: ReactNode` to `KanbanColumn`; `title` becomes the plain label.
Kanban renders `headerExtra` only in the header next to the existing count (`:69-70`).
OpportunityBoardPage passes the formatted total as `headerExtra`. `Kanban.test.tsx:39` already
asserts `"Move to Won"` — the plain-title behaviour — so it starts passing rather than needing a
rewrite; add one assertion that `headerExtra` content does NOT appear in the menu or
`aria-label`, and one that `itemLabel` reaches the move-button label.

- [ ] Failing test additions → `Kanban.tsx` + `OpportunityBoardPage.tsx` → green →
      commit `fix(frontend): kanban a11y — totals out of aria-labels and the move menu` →
      PR closes #163.

---

## #164 — FormBuilder `required` is decorative

**Root cause.** `submit()` is `preventDefault()` + `onSubmit()` with no checks
(`FormBuilder.tsx:146-149`) under `<form noValidate>` (`:152`); `required` renders only as an
`aria-hidden` red `*` (`:170-174`) and is forwarded to the `<select>` branch alone (`:93`) —
inputs (`:122-132`), textareas (`:80-87`) and checkboxes never receive it. `errors` is a
caller-owned prop (`:36, :189-192`); the component has nowhere to put a client-side error. 37
pages import it, so the fix must live inside the component with zero caller changes.

**Fix (decision: controlled validation, keep `noValidate`).** Native bubbles would fight the
component's own error rendering and its controlled state; the component already owns an error
slot per field, so use it. In `submit()`: compute missing required values from `fields` (empty
string / undefined / null; unchecked checkboxes are *not* "missing" unless we ever add a
`requiredTrue` — YAGNI), hold them in local `clientErrors` state merged over the `errors` prop
(prop wins on collision), focus the first offending field, and bail before `onSubmit()`. Clear a
field's client error on change. Also forward `required` to all input branches for the
`aria-required` semantics (with `noValidate` kept, the browser adds no competing UI).

**Tests** (extend `FormBuilder.test.tsx`): empty-required submit calls `onSubmit` zero times and
renders the message under the field; filling the field clears it on change; a caller-supplied
`errors` entry survives and wins; a form with no required fields submits exactly as today.

- [ ] Failing tests → implement → green → commit
      `fix(frontend): FormBuilder enforces required fields before submit` → PR closes #164.

---

## #165 — A fresh tenant's admin cannot read what its own template created

**Root cause.** Onboarding grants the admin role *before* applying the template and never widens
it (`industry/onboarding.py:85-88`); the role is hardcoded to `_ADMIN_PERMISSION_KEYS` — six
`admin.*` keys, zero `finance.*`/`inventory.*` reads (`admin/service.py:29-36`, `:157-176`). So
the first human in a new tenant sees Home + Admin (`shell/HomePage.tsx:17-18` gates on
permissions) while the COA and tax codes their own template just instantiated are unreadable.

**Decision this plan takes (flag in the PR for Taha):** a fresh tenant's first admin is a
**Superuser minus platform permissions** — the full synced catalog except `onboarding.tenant.create`
(deliberately a platform action, `core/bootstrap.py:134-138`; that half of the issue is by
design and stays). Precedent: `seed.py:385-386` builds exactly this role from `catalog_keys()`
after `sync_permission_catalog`. The alternative (curate a "tenant admin" subset) is a policy
nobody has asked for and a second list to rot.

**Fix.** Give `grant_admin_role` an explicit `permission_keys: Sequence[str]` parameter
(default: today's `_ADMIN_PERMISSION_KEYS`, so existing callers are untouched); onboarding calls
`sync_permission_catalog` then passes `catalog_keys()` minus the platform keys. `create_role`
already validates keys against the synced catalog (`admin/service.py:100-135`), so ordering is
sync-then-grant.

**Tests** (`backend/tests/modules/industry/` — find the onboarding test file): after onboarding,
the admin's `/me` permissions include `finance.account.read` (or the real key — read the catalog)
and exclude `onboarding.tenant.create`; the admin can list the template's COA; existing
`grant_admin_role` callers still produce the narrow role.

- [ ] Failing tests → implement → green → commit
      `fix(admin): a new tenant's first admin can read what onboarding created` → PR closes #165.

---

## #166 — Report grid/CSV headers show wire names

**Root cause.** The grid takes `header: name` straight off `ReportResult.columns`
(`ReportBuilderPage.tsx:161-167`), and the CSV writes the same `names` list
(`report_builder.py:295`, built at `:166-194` — aggregate aliases minted as `count_{col}` /
`{func}_{column}` at `:149`/`:162`). Labels exist and are already in the browser — the same page
renders `column.label` in its pickers (`ReportBuilderPage.tsx:230, 263, 359, 407`) from
`ReportColumnDescriptor` (`reporting/schemas.py:145-153`).

**Fix, both surfaces from one source so they stay consistent (the issue's own requirement):**
- Backend: `_selected` returns `(names, labels)` — a plain column's label from the registry
  (`report_registry.py:73`), an aggregate's label composed as `f"{FUNC_LABEL[func]} of {label}"`
  (`Count of Order number`); the CSV emits labels at `:295`; `ReportResult` gains
  `column_labels: list[str]` alongside `columns` (additive, no client break).
- Frontend: grid headers use `result.column_labels` with `result.columns` as fallback
  (`ReportBuilderPage.tsx:164`).

**Tests:** backend — a grouped+aggregated run returns labels aligned index-for-index with
`columns`, and the CSV's first line shows them (extend the existing report-builder tests); the
pure header-mapping logic on the frontend goes to
`ReportBuilderPage.test.ts` (the file already exists — the repo's one page-logic test).

- [ ] Failing tests → implement → green → commit
      `fix(reporting): human labels on report grid and CSV headers` → PR closes #166.

---

## #176 — Nine files over the STRUCTURE §8.4 caps

**Ground truth at 2026-08-15** (`wc -l`, vs the issue body): `mrp.py` shrank to exactly 400 —
*at* the cap, and STRUCTURE.md:123 says "at the cap, split", so it stays in scope; the four
frontend pages each grew a few lines; `router.tsx` is 1504.

Split-only refactors, **zero behaviour change**, one commit each so any regression bisects to one
file. Seams (verified against each file's structure):

| File (lines) | Split |
|---|---|
| `backend/.../manufacturing/service/mrp.py` (400) | demand + BOM explosion (`_gather_independent_demand` `:87` → `_bom_graph` `:217-264`) → `service/mrp_planning.py`; run persistence + job stays |
| `backend/.../inventory/service/costing.py` (402) | the three appliers (`_apply_inbound` `:171`, `_apply_outbound` `:216`, `_apply_transfer` `:268-336`) → `service/costing_apply.py` (sibling naming: `costing_fifo.py` et al. exist) |
| `backend/.../finance/service/fx_revaluation.py` (402) | posting/reversal (`_post_entry_with_lines` `:154` → `_reverse_previous_run` `:219-289`) → `service/fx_revaluation_post.py`; move `list_revaluation_runs` (`:386`) to `finance/queries.py` where reads live |
| `frontend/src/router.tsx` (1504) | per-module `modules/<module>/routes.tsx` exporting a route array, keyed off the existing `// --- <Module>` banners (`:212`…`:1287`); root/login + `routeTree` composition stays. **Do this one LAST** — every other open frontend PR touches it |
| `frontend/.../ReportBuilderPage.tsx` (491) | the three JSX cards (Columns `:216-238`, Filters `:239-343`, GroupBy+Aggregations `:344-430`) → `modules/reporting/components/` |
| `frontend/.../ProductionOrderDetailPage.tsx` (361) | `FinishSection` (`:36-146`) → `modules/manufacturing/components/FinishSection.tsx` |
| `frontend/.../BomFormPage.tsx` (359) | `BomComponentsSection` (`:48-220`) → components/ |
| `frontend/.../RoutingFormPage.tsx` (337) | `RoutingOperationsSection` (`:40-204`) → components/ |
| `frontend/.../TimesheetDetailPage.tsx` (315) | `EntryAddRow` (`:37-143`, takes `CELL_INPUT` `:35` with it) → `modules/hr/components/EntryAddRow.tsx` |

**Verification per split:** the full suite (or `npm run typecheck && npm run test && npm run
build`) green with **no test edits** — a split that needs a test change was not behaviour-free.
The hospitality `models.py` split, if Phase 20 Task 3 needs it, follows this same rule there.

- [ ] Nine commits (or one PR of nine commits, `router.tsx` last) → PR closes #176.

---

## Suggested order

#163 → #164 (same component neighbourhood, both a11y-adjacent), #166, #165 (the one needing
Taha's eye on the permission decision), #176 last (pure debt, and its `router.tsx` split wants
the hospitality UI routes from the P1 plan merged first so they move once, not twice).
