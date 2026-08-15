# STRUCTURE.md — Folder Structure, Naming & File-Handling Protocol for Atlas ERP

Place this file at the repo root alongside CLAUDE.md and GITHUB-WORKFLOW.md, and add to CLAUDE.md: "All file creation, naming, and placement MUST follow STRUCTURE.md. Re-read it after any compaction." The rule of this document: **every file has exactly one correct home, and its name alone tells you what's inside it.** When you are unsure where something goes, the answer is in here — do not invent a new location.

# 1. Canonical Repository Tree

```
atlas-erp/
├── CLAUDE.md  PLAN.md  PROGRESS.md  DECISIONS.md
├── GITHUB-WORKFLOW.md  STRUCTURE.md  PERFORMANCE.md
├── README.md  LICENSE  NOTICE  CONTRIBUTING.md  SECURITY.md
├── .gitignore  .dockerignore  .env.example  Makefile
├── docker-compose.yml  docker-compose.prod.yml
├── .github/
│   ├── workflows/ci.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/{bug.yaml,feature.yaml}
├── docs/
│   ├── architecture.md  api.md  industry-templates.md  deployment.md
│   ├── DESIGN.md  PRODUCT.md    # frontend visual system + product register (PLAN 15.1)
│   ├── research/               # s4hana-parity.md + later market scans
│   ├── modules/            # one guide per module: finance.md, inventory.md, ...
│   └── assets/             # diagrams/screenshots referenced by docs ONLY
├── industry-templates/
│   ├── _schema.yaml        # the template JSON-Schema, single source of truth
│   └── {manufacturing,retail,professional-services,healthcare,construction,hospitality}.yaml
├── backend/
│   ├── pyproject.toml  alembic.ini  Dockerfile  .dockerignore
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py         # app factory + router mounting, nothing else
│   │   ├── core/           # cross-cutting only — see §2
│   │   └── modules/        # business modules — see §3
│   ├── tests/              # mirrors app/ — see §6
│   └── seed.py
└── frontend/
    ├── package.json  vite.config.ts  tsconfig.json  index.html
    ├── Dockerfile  nginx.conf  .dockerignore
    └── src/
        ├── main.tsx  App.tsx  router.tsx
        ├── lib/            # api client, auth, query hooks, formatters
        ├── components/     # design system, module-agnostic — see §4
        └── modules/        # one folder per ERP module, mirrors backend names
```

Nothing lives outside this tree. No `scratch/`, `tmp/`, `old/`, `backup/`, or `misc/` directories — ever. Temporary experiments happen on a branch and are deleted, not parked in the tree.

# 2. `backend/app/core/` — what belongs and what doesn't

One file per cross-cutting concern, flat, no subpackages: `config.py`, `db.py` (engine, session, tenant filter), `tenancy.py`, `auth.py`, `rbac.py`, `audit.py`, `events.py` (bus + base event class), `docflow.py`, `models.py` (Base, mixins: TenantMixin, AuditMixin, TimestampMixin), `schemas.py` (shared Pydantic bases, pagination envelope, error envelope), `numbering.py` (document sequences), `money.py` (Money/Quantity/Rate type decorators, quantize + largest-remainder allocate — added by D-015), `custom_fields.py` (custom-field defs registry, validation, JSON column helper — added by D-016), `exceptions.py`, `deps.py` (FastAPI dependencies).

**Litmus test:** if a file mentions a specific business concept (invoice, item, employee), it does NOT belong in `core/` — move it to its module. If two modules need the same business logic, the dependency-rule in §5 decides who owns it; `core/` is never the dumping ground.

# 3. `backend/app/modules/` — identical anatomy for every module

Module package names (fixed, never abbreviate differently elsewhere): `finance`, `inventory`, `procurement`, `sales`, `manufacturing`, `quality`, `maintenance`, `hr`, `projects`, `crm`, `reporting`, `admin`, `industry`, `hospitality`.

Every module has exactly this internal shape — no exceptions, no creativity:

```
modules/finance/
├── __init__.py
├── models.py        # SQLAlchemy models (split into models/ package only if >600 lines: models/journal.py, models/accounts.py, each <400)
├── schemas.py       # Pydantic request/response (same split rule)
├── service.py       # ALL business logic (split rule: service/ package, one file per aggregate: service/journal.py, service/payments.py)
├── router.py        # thin HTTP layer only: parse → call service → return schema
├── events.py        # events this module PUBLISHES (definitions) 
├── handlers.py      # subscriptions to OTHER modules' events
└── constants.py     # enums, status values, magic numbers — no literals inline elsewhere
```

A new file type may not be invented per-module. If finance needs `depreciation.py`, it goes inside `service/` as `service/depreciation.py`, not as a new top-level module file.

# 4. Frontend structure

- `src/components/` is the design system: one folder per component (`DataGrid/`, `FormBuilder/`, `Kanban/`, `KpiCard/`, `DocFlowViewer/`), each containing `ComponentName.tsx`, optional `ComponentName.test.tsx`, and `index.ts` re-export. Components here know NOTHING about ERP concepts — they take data and callbacks.
- `src/modules/<module>/` mirrors backend module names exactly and contains: `pages/` (route components, named `<Entity>ListPage.tsx`, `<Entity>DetailPage.tsx`, `<Entity>FormPage.tsx`), `components/` (module-specific composites), `api.ts` (typed endpoint calls for this module only), `types.ts` (mirrors backend schemas), `hooks.ts` (TanStack Query hooks: `useJournalEntries`, `usePostJournal`).
- `src/lib/`: `apiClient.ts` (the ONLY place fetch/axios appears), `auth.ts`, `queryClient.ts`, `format.ts` (money, dates, quantities — all display formatting goes through here, never inline `toFixed`).
- No barrel-exporting whole modules into each other; cross-module UI reuse means the component was design-system material and must be promoted to `src/components/`.

# 5. Dependency Rules (what may import what)

- `core` imports nothing from `modules`. Modules import `core` freely.
- Modules never import each other's `service.py` or `models.py` directly. Cross-module effects go through the event bus (`finance/handlers.py` reacts to `inventory` events). Cross-module reads needed synchronously (e.g., sales needs an item's price) go through a small, explicit query interface the owning module exposes in `modules/<owner>/queries.py` — plus `modules/<owner>/events.py` (declarative event dataclasses only, no logic), the two files another module may import (events.py allowance added by D-011 so handlers can subscribe to typed events).
- Dependency direction for queries: finance is the bottom (everyone may use finance/queries), then inventory, then everything else. Two modules may never import each other's queries bidirectionally — if that seems needed, the shared concept is misplaced; file an issue and resolve ownership before coding.
- Frontend: `modules/*` may import `lib` and `components`; `components` and `lib` never import from `modules`.

# 6. Tests mirror source, exactly

`backend/tests/` replicates `app/` paths: code in `app/modules/finance/service/journal.py` is tested in `tests/modules/finance/test_journal.py`. Shared fixtures live in `tests/conftest.py` (db session, tenant factory, auth client) and `tests/modules/<module>/conftest.py` for module fixtures. Test names state the rule being proven: `test_journal_rejects_unbalanced_lines`, `test_posting_to_closed_period_raises`. One assertion-theme per test. Frontend tests sit beside the file they test (`DataGrid.test.tsx`). A regression test for issue #NN includes `#NN` in its docstring/comment.

# 7. Naming Conventions (single table of truth)

| Thing | Convention | Example |
|---|---|---|
| Python files/modules | snake_case, singular concern | `journal.py`, `stock_move.py` |
| Python classes | PascalCase, no abbreviations | `JournalEntry`, `StockMove`, `PurchaseOrderLine` |
| Python functions/vars | snake_case verbs for actions | `post_journal_entry()`, `reserve_stock()` |
| Pydantic schemas | Entity + suffix `Create/Update/Read/Filter` | `JournalEntryCreate`, `ItemRead` |
| DB tables | snake_case plural, module prefix | `fin_journal_entries`, `inv_stock_moves`, `sls_orders` |
| DB columns | snake_case; FKs `<entity>_id`; money pairs `amount`+`currency_code`; booleans `is_/has_` | `is_posted`, `cost_center_id` |
| Enums (Py + DB values) | Class PascalCase, values UPPER_SNAKE stored as strings | `OrderStatus.PARTIALLY_SHIPPED` |
| Alembic revisions | `NNNN_short_description` sequential | `0007_add_asset_register` |
| Domain events | PascalCase past tense, module-prefixed string key | class `SalesOrderShipped`, key `sales.order.shipped` |
| Permissions | `module.entity.action` lowercase | `finance.journal.post` |
| API routes | `/api/v1/<module>/<resource-kebab-plural>`; actions as sub-resources, never verbs in resource names | `/api/v1/finance/journal-entries/{id}/post` |
| JSON fields | snake_case (mirror backend; frontend types match, no camelCase translation layer) | `posting_date` |
| TS files | Components PascalCase.tsx, everything else camelCase.ts | `DataGrid.tsx`, `apiClient.ts` |
| TS types/interfaces | PascalCase, no `I` prefix | `JournalEntry` |
| React hooks | `use` + Entity + verb | `usePostJournalEntry` |
| CSS | Tailwind utilities only; the rare custom class kebab-case in one `index.css` | `doc-flow-edge` |
| Env vars | `ATLAS_` prefix UPPER_SNAKE | `ATLAS_DATABASE_URL` |
| Docs files | kebab-case | `industry-templates.md` |
| Branches/commits/labels | as defined in GITHUB-WORKFLOW.md | — |

Terminology lock: the same business concept uses the same word everywhere — code, DB, API, UI, docs. It is `item` (not product/article/sku interchangeably), `vendor` (not supplier), `customer`, `warehouse`, `journal entry`. Industry templates may override the *display* label, never the internal name. Record any new canonical term in DECISIONS.md the moment you coin it.

# 8. File-Handling Rules

1. **Search before create.** Before creating any file, check whether its correct home already exists (`ls`, `grep -r "class JournalEntry"`). Duplicate implementations are a `severity:major` issue.
2. **No versioned filenames.** Never `service_v2.py`, `utils_new.py`, `final_fixed.tsx`. Improving a file means editing it; git holds history.
3. **No orphan files.** Every file is imported/referenced by something or it doesn't exist. When refactoring away from a file, delete it in the same commit.
4. **Size limits.** Hard cap 400 lines per Python file and 300 per TSX component; at the cap, split along the rules in §3/§4 — never split into `part1/part2`.
5. **One concept per file.** A file named `journal.py` containing tax logic is misfiled even if it compiles. Filename promises content.
6. **Generated files are never hand-edited** (OpenAPI dumps, lockfiles, migration auto-generations get reviewed and adjusted only through their tooling). Commit lockfiles; never commit build output, caches, coverage reports, or `__pycache__` — keep `.gitignore` authoritative.
7. **No utils graveyards.** Before adding to a `utils`-like file, ask which module/concern owns the function; `core/` files and `lib/format.ts` are the only sanctioned shared helpers, each scoped by its filename.
8. **Imports:** absolute imports only in backend (`from app.modules.finance.service import journal`); frontend uses the `@/` alias (`@/lib/apiClient`). No relative `../../..` chains.
9. **Module READMEs are forbidden** — module docs live in `docs/modules/<module>.md` only, so documentation has one home.
10. **Renames/moves** are their own commit (`refactor(structure): move costing into inventory/service/costing.py`), never mixed with logic changes, so history stays traceable.
11. **Deletions** follow issue-first if the file contains live logic being retired: file the issue, explain replacement, delete in the fix PR.
12. **After compaction:** before creating ANY new file, re-read this document and run `git status` + `tree -L 3` (or `find`) to re-anchor on the actual current structure. Never recreate from memory a file that might already exist.

# 9. Self-Check (append result to PROGRESS.md at each session end)

Any file outside the canonical tree? Any file over the size cap? Any duplicate concept names (`grep` a few suspects)? Any orphan files? Any module breaking the dependency rules? Any term drift (supplier vs vendor)? Each "yes" becomes a `tech-debt` issue per GITHUB-WORKFLOW.md §6, fixed before the next promotion.
