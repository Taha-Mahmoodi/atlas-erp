# Industry Templates

Atlas ships six **industry templates** (PLAN 14.1 / D-060) — the configuration layer that makes the
platform industry-aware, Atlas's answer to SAP industry solutions. A tenant picks one at onboarding
and its whole configuration is instantiated in one transaction. This is the **authoring reference**;
the module/loader internals are in [docs/modules/industry.md](modules/industry.md).

## Where they live

```
industry-templates/
├── _schema.yaml            # the JSON-Schema (single source of truth) the loader validates against
├── manufacturing.yaml
├── retail.yaml
├── professional-services.yaml
├── healthcare.yaml
├── construction.yaml
└── hospitality.yaml
```

The loader (`backend/app/modules/industry/loader.py`) reads a template, **validates it against
`_schema.yaml`**, then parses it into a typed `IndustryTemplate`. The schema is the single source of
truth: closed whitelists for terminology terms and module keys, enums for account types / costing
methods / custom-field types, and patterns for codes — a typo or unknown key is rejected with a
JSON-pointer path.

## The schema (`_schema.yaml`)

| Section | Shape | Applied by |
|---|---|---|
| `name` / `display_name` / `description` | the machine key (= file stem, one of the shipped names) + human labels | — |
| `terminology` | canonical-term → display-label map (closed whitelist of terms) | industry → admin TenantSetting |
| `chart_of_accounts` | `{groups: [{code, name, parent_code?, sort_order?}], accounts: [{code, name, account_type, group_code?, cash_flow_category?, is_cash_equivalent?, is_postable?}]}` | **finance** handler |
| `tax_codes` | `[{code, name, rate_percent (string %), jurisdiction?, is_inclusive?}]` | **finance** handler |
| `currencies` | `[{code, name, decimal_places?, is_functional?}]` — exactly one functional | **finance** handler |
| `uoms` | `[{code, name}]` | **inventory** handler |
| `item_categories` | `[{code, name, default_costing_method}]` (MOVING_AVERAGE\|FIFO) | **inventory** handler |
| `modules` | module-key → enabled flag (closed whitelist) | industry → admin TenantSetting |
| `custom_fields` | `[{entity_key, field_key, label, type, required?, default?}]` (type STRING\|NUMBER\|DECIMAL\|BOOL\|DATE) | industry → `core/custom_fields` (D-016) |
| `approval_presets` | `{purchase_order_threshold?, requisition_threshold?, currency_code?}` (thresholds strings) | **procurement** handler |
| `numbering_formats` | sequence-name → `{prefix, padding, year_reset?}` | industry → `core/numbering` (D-012) |

Money-bearing values (tax `rate_percent`, approval thresholds, DECIMAL custom-field defaults) are
**strings** (D-015 no-float), parsed exactly via `Decimal` when the rows are created.

## The templates — how they differ

The spec requires *meaningfully different* templates. The distinctives (all asserted in
`test_templates_valid.py`):

| Template | Terminology | Modules | Costing default | Defining COA / custom fields |
|---|---|---|---|---|
| **manufacturing** | Production Order, Material, Plant | **ALL on** | MOVING_AVERAGE | WIP + Finished Goods + Production Variance accounts; an engineering-revision field |
| **retail** | Store, Product, Shopper | manufacturing **off**, projects off, quality/maintenance off | **FIFO** | Merchandise Inventory + Shrinkage; **barcode** + shelf-location fields on the item |
| **professional-services** | Engagement, Consultant, Client | inventory **off**, manufacturing off, projects **on** | (no inventory) | Unbilled-Receivables/WIP + Consulting Fees; **billable_rate** + utilization fields on the employee, engagement-partner on the project |
| **healthcare** | **Patient**, Encounter, Claim | manufacturing **off**, CRM off | FIFO | Patient + Insurance Receivables, Contractual Allowances; a required **insurer/payer** field + policy + DOB on the customer |
| **construction** | **Job** (project + production order), Owner, Subcontractor | manufacturing **off**, projects on, maintenance on | MOVING_AVERAGE | **Retainage Receivable/Payable** + Costs/Billings-in-Excess; a **retainage_percent** field on the customer, contract-number + bond-required on the project |
| **hospitality** | **Guest / Group Account**, Storeroom, Folio Invoice | hospitality **on**, manufacturing on (BOM sub-engine only — recipes are BOMs; no production orders/MRP), projects off | **FIFO** | **Guest Ledger / City Ledger / Advance Deposits** as three separate control accounts (spec Q5) + Room/Food/Beverage revenue split; star-rating + check-in/out-time fields on the property (tenant) |

No two templates ship the same terminology map, module set, or COA.

## How the loader applies a template (idempotent, one transaction)

`apply_template(session, tenant_id, name)`, inside `run_in_uow` under `system_context`:

1. records the `TenantIndustryConfig` (one per tenant — the idempotency anchor);
2. applies the **core/admin slices directly** — custom-field defs (`core/custom_fields`), numbering
   sequences (`core/numbering`), terminology + module-toggle TenantSettings (admin);
3. **publishes `IndustryTemplateApplying`** — finance, inventory and procurement each create their
   slice idempotently in their `handlers.py` (the §5-clean seam; industry never imports their
   services).

**Idempotency:** re-applying the same template is a no-op (every create is skip-if-exists / upsert);
applying a *different* template is rejected (`industry.template_conflict`). Any handler failure rolls
the **whole** apply back.

## API

| Method | Path | Permission |
|---|---|---|
| GET | `/api/v1/industry/templates` | `industry.template.read` |
| GET | `/api/v1/industry/templates/{name}` | `industry.template.read` |
| POST | `/api/v1/industry/tenants/{tenant_id}/apply?template=` | `industry.template.apply` (own tenant only) |

The apply is tenant-scoped: an admin may apply only to their **own** tenant; cross-tenant
provisioning is the system/onboarding path (PLAN 14.2). The onboarding wizard (14.2) wraps this apply.

## Adding a template

1. Add `{name}.yaml`; add `name` to `SHIPPED_TEMPLATES` (`industry/constants.py`) and the `name` enum
   in `_schema.yaml`.
2. Declare every required section; `name` must equal the file stem; exactly one functional currency.
3. The `SHIPPED_TEMPLATES`-parametrized validation test picks it up automatically; add a distinctness
   assertion for its defining feature.
