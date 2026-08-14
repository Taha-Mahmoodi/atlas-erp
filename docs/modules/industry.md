# Industry (`backend/app/modules/industry/`)

The industry module is the **INDUSTRY CONFIGURATION LAYER** (Phase 4 of the product spec / PLAN
14.1) — Atlas's answer to SAP industry solutions and the product's headline differentiator. A tenant
picks one of the shipped templates at onboarding and the loader instantiates its whole
configuration — COA preset, tax codes, currencies, UoMs, item categories, typed custom fields,
approval presets, module toggles, terminology overrides and numbering formats — in **one
transaction**.

The normative design lives in **D-016** (custom fields, in [docs/architecture.md](../architecture.md))
and **D-060** (the industry layer, in [DECISIONS.md](../../DECISIONS.md)); this guide is the
operator/contributor map. See also [docs/industry-templates.md](../industry-templates.md) for the
template-authoring reference.

## Status

**PLAN 14.1 is COMPLETE** — the YAML schema, the validating idempotent loader, the shipped templates,
the core custom-field registry (D-016), and the per-module event-bus provisioning.

| File | Concern |
|---|---|
| `constants.py` | the shipped-template names, the provisioning-event key, the terminology/module-toggle TenantSetting keys, the `industry.template.read`/`.apply` permission keys |
| `schemas.py` | the parsed-template Pydantic models (`IndustryTemplate` + sub-specs), mirroring `_schema.yaml` |
| `schema_validator.py` | a dependency-free JSON-Schema validator (the subset `_schema.yaml` uses) |
| `loader.py` | `load_template(name)` (read + schema-validate + parse) and `apply_template(...)` (the idempotent provisioning path) |
| `events.py` | `IndustryTemplateApplying` — the provisioning event carrying the validated template |
| `models.py` | `TenantIndustryConfig` (`ind_tenant_industry_configs`) — the applied-template record per tenant |
| `queries.py` | `list_templates`, `get_applied_template`, `terminology_for` — the cross-module/UI read surface |
| `router.py` | `GET /templates`, `GET /templates/{name}`, `POST /tenants/{tenant_id}/apply?template=` |

The templates themselves are **YAML data**, not code: `industry-templates/_schema.yaml` (the schema,
single source of truth) + the `{manufacturing,retail,professional-services,healthcare,
construction,hospitality}.yaml` files (STRUCTURE §1, a top-level repo dir). Hospitality is the
sixth, added by PLAN 19.1 alongside the hospitality module.

## The loader + idempotency

`load_template(name)` reads `industry-templates/{name}.yaml`, validates the raw dict against
`_schema.yaml` (the declarative gate — closed whitelists for terminology terms / module keys, enums,
patterns), then parses it into a typed `IndustryTemplate`. Pure + cached (the files are immutable at
runtime).

`apply_template(session, tenant_id, name)` is the idempotent provisioning path, run inside
`run_in_uow` (D-011) under `system_context` (D-007 provisioning):

1. resolve the existing `TenantIndustryConfig` — re-applying the **same** template is a **no-op**
   (the core get-or-create + the handlers' skip-if-exists make the second pass harmless); applying a
   **different** template raises `ConflictError` (`industry.template_conflict` — a tenant's industry
   is chosen **once** at onboarding; switching would orphan the first template's COA/fields, out of
   v1 scope);
2. record the config row;
3. apply the **core/admin-owned** slices directly;
4. **publish** `IndustryTemplateApplying` — the **cross-module** slices are created by the owning
   modules' provisioning handlers.

Because the whole apply is one unit of work, any handler failure rolls the **whole** thing back — a
half-applied template can never persist (proven by `test_apply_is_one_transaction`).

## The event-bus provisioning (§5: which module applies which slice)

The industry module must **not** import finance/inventory/procurement services (STRUCTURE §5). So the
cross-module writes go through the **event bus** (the codebase-wide provisioning pattern):

| Slice | Owner | How |
|---|---|---|
| Currencies, COA groups + accounts, tax codes | **finance** | `finance/handlers/provisioning.py` → `provision_finance_for_template` (subscribes to `IndustryTemplateApplying`) |
| UoMs, item categories | **inventory** | `inventory/handlers.py` → `provision_inventory_for_template` |
| Approval presets (PO + requisition thresholds) | **procurement** | `procurement/handlers.py` → `provision_procurement_for_template` |
| Custom-field defs (D-016) | **core** (industry applies directly) | `core/custom_fields.ensure_field_def` |
| Numbering sequences (D-012) | **core** (industry applies directly) | `core/numbering.ensure_sequence` |
| Terminology overrides + module toggles | **admin** TenantSetting (industry applies directly) | `adm_tenant_settings` upsert |

Each handler creates its slice **idempotently** (skip-if-exists by the natural code key) so re-apply
never duplicates and a retry completes cleanly. The handlers are registered in
`app.core.bootstrap.register_event_handlers` (the D-011 seam). **One-directional, no cycle:** industry
imports core + admin (models) and publishes the event; finance/inventory/procurement import
`industry/events` (declarative event + the typed `IndustryTemplate`) only — never each other's
services. Nothing imports `industry/service`.

## Custom fields (D-016)

The custom-field registry is **core-owned** (`core/custom_fields.py` + `core_custom_field_defs`), NOT
industry-owned — industry-module ownership would force finance/inventory to import upward (a STRUCTURE
§5 violation). The industry loader is the **first writer** of defs; an admin CRUD endpoint can write
more later. Three pieces:

- `CustomFieldDef` — one registered field for an `entity_key` (e.g. `inventory.item`), with a flat
  `field_key`, a `data_type` (STRING|NUMBER|DECIMAL|BOOL|DATE), `is_required`, `is_active`
  (soft-deactivation, never hard delete), `default_value` (stored portably as a string);
- `custom_fields_column()` — the JSONB/JSON column an extensible entity opts into (models opt in over
  time; not retrofitted onto every model now);
- `validate_custom_fields(defs, values)` — the owning-module services' gate: unknown keys rejected,
  required enforced, per-type coercion, **DECIMAL as a string** (D-015 no-float), DATE ISO-8601.

The **report builder** (13.2) + forms/grids read defs via `list_field_defs(entity_key)` to surface
custom columns. **Custom fields are invisible to DB constraints by design** — they are
descriptive/reporting fields; anything participating in a financial invariant must be a **real
column**, never a custom field.

## How to add a template

1. Create `industry-templates/{name}.yaml`; add `name` to `SHIPPED_TEMPLATES` in
   `industry/constants.py` and the `name` enum in `_schema.yaml`.
2. Fill every required section; the `name` field must equal the file stem; declare exactly one
   functional currency.
3. `test_templates_valid.py` (`-m "not pg and not perf"`) validates + parses it automatically (the
   `SHIPPED_TEMPLATES`-parametrized test); add a distinctness assertion for its defining feature.
