# CRM (`backend/app/modules/crm/`)

CRM is the **tenth business module** (PLAN 12.1), the **CRM-lite pre-sales pipeline**, sitting at the
**top of the dependency order** (STRUCTURE §5 / **D-057**). It is the deliberately small CRM core the
[parity doc](../research/s4hana-parity.md) scopes: **leads** that **qualify and convert** into
**opportunities**, an opportunity **kanban** whose **stage is the column**, **activities** logged
against leads/opportunities, and the headline **convert-to-customer+quote** that turns a won
opportunity into a real sales `Customer` + `Quote`. Everything else CRM (campaigns, marketing
automation, contact/account hierarchies, forecasting/pipeline analytics, service tickets, opportunity
teams/competitors) is **out of v1** — recorded in the parity doc.

The normative design lives in [docs/architecture.md](../architecture.md) (D-011 event bus, D-012
docflow/numbering, D-029 opaque cross-module ids, D-015 money types, D-014 pagination, D-009 RBAC) and
the **D-057** decision in [DECISIONS.md](../../DECISIONS.md); this guide is the operator/contributor
map.

## Status

**PLAN 12.1 is COMPLETE** — this **opens and closes Phase 12 (CRM)**. Lead CRUD + qualify/disqualify +
convert-to-opportunity, opportunity CRUD + lines + the kanban move-stage + the kanban board, activity
CRUD + complete/cancel, and the opportunity → customer + quote convert via the event bus are all live.

## The pipeline

```
Lead  ──qualify──▶ QUALIFIED ──convert──▶ Opportunity (PROSPECTING)
 │                                              │
 └─disqualify─▶ DISQUALIFIED                    │ move-stage (the kanban move)
                                                ▼
                          PROSPECTING ─ QUALIFICATION ─ PROPOSAL ─ NEGOTIATION ─▶ WON | LOST
                                                                                    │
                                                                  convert ──▶ sales Customer + Quote
```

### Leads (`crm_leads`)

An unqualified inbound contact (company/contact/email/phone, source, estimated value). Auto-numbered
**`LEAD-…`** (gapless per-tenant, claimed at creation). `status` runs **NEW → CONTACTED → QUALIFIED →
CONVERTED** (or **DISQUALIFIED**). A **QUALIFIED** lead converts to an opportunity:
`convert_lead_to_opportunity` builds the opportunity (copying company/contact/value/currency), links
`source_lead_id`, and sets the lead's `converted_opportunity_id` + status **CONVERTED**. The lead →
opportunity conversion is wholly CRM-internal (no cross-module event), so it is `crm.lead.manage`-gated.

### Opportunities (`crm_opportunities`)

A qualified deal in the pipeline. Auto-numbered **`OPP-…`** and registered in `core_documents` (so the
convert handler can write the docflow edge to the quote). **`stage` IS the kanban column**:
**PROSPECTING → QUALIFICATION → PROPOSAL → NEGOTIATION → WON | LOST**; `move_stage` moves the card.

- **Allowed stage moves:** any **open** stage (PROSPECTING/QUALIFICATION/PROPOSAL/NEGOTIATION) → any
  other open stage (forward *or* backward — a deal can slip), or → **WON/LOST** (closing it). A
  **terminal** stage (WON/LOST) cannot move — the deal is closed; reopening would be a new
  opportunity. Moving to the same stage is rejected.
- `customer_id` (optional, opaque sales id, validated) links an **existing** customer; when NULL the
  deal is for a **prospect** named by `company_name` (convert then creates the customer).
- **`OpportunityLine`** (`crm_opportunity_lines`, optional "expected products"): one row per item the
  deal expects to sell (`item_id` opaque inventory id + `quantity` + `estimated_unit_price`). **These
  become the quote lines on convert.**

### Activities (`crm_activities`)

A logged interaction (`activity_type` CALL/EMAIL/MEETING/TASK/NOTE) against **exactly one** of a lead
**or** an opportunity. `status` runs **OPEN → COMPLETED | CANCELLED** (complete stamps
`completed_date`).

**The exactly-one-parent rule:** an activity references **exactly one** of `lead_id` / `opportunity_id`
— never zero, never both. This is enforced **twice**: the service validates it up front (a friendly
`422 crm.activity_parent_invalid`) and also that the named parent exists, and the DB CHECK
`ck_crm_activities_one_parent` (`lead_id XOR opportunity_id`) is the bypass-proof backstop.

## The kanban board

`GET /api/v1/crm/opportunities/kanban` (perm `crm.opportunity.read`, optional `owner_employee_id`)
returns the opportunities grouped into a **column per stage**, in the declared stage order (the four
open columns then WON, LOST). Each column carries its `count`, `total_estimated_value`, and the
(capped) cards. It is a **bounded view** (PERFORMANCE §6): **one** query loads the opportunities,
grouped in memory — no per-stage N+1; each column is sliced to a per-column cap.

## The convert-to-customer+quote (the headline)

Converting an opportunity creates a sales **Customer** + **Quote** — both **sales-owned** writes. CRM
**must not** call sales' service (STRUCTURE §5). So `convert_opportunity` (perm
**`crm.opportunity.convert`**, a *distinct* higher-privilege key) **publishes** an
**`OpportunityConverted`** event, and **sales' `handlers.py`** (`create_customer_and_quote_for_conversion`,
subscribed at the D-011 seam) creates the customer (only when the opportunity is not already linked to
one) + the quote through **sales' own service**, in the **same transaction** (drained by `run_in_uow`).
This mirrors the billing → AR-invoice and planned-buy → requisition precedents, with the roles
flipped (CRM publishes, sales creates).

- **Atomic (D-011):** any handler failure (a duplicate customer code on re-convert, an unknown item,
  an unpriceable line) rolls the **whole** convert back.
- **Idempotent / non-repeatable:** a **WON** (already-converted) opportunity cannot re-convert; a
  **LOST** opportunity is not convertible — both rejected by the CRM service **before** any event
  publishes.
- **Needs ≥1 line:** a quote line must reference a real inventory item, so an opportunity with **no**
  expected-product lines cannot convert (`422 crm.opportunity_no_lines`). The
  "single-line-from-estimated_value" fallback is **not viable in v1** (a quote line needs a real item);
  the operator adds at least one line before converting.
- **Recording the link:** the **durable** convert link is the **docflow edge** the sales handler
  writes (opportunity document → `converted_to_quote` → quote document). A sales `Customer` is a
  **master** (not a docflow document — no `core_documents` entry), so there is **no** opportunity →
  customer docflow edge; the customer link is the opportunity's recorded opaque `converted_customer_id`.
  CRM **pre-generates** the new customer id (for a prospect) + the quote id and passes them in the
  event so the handler creates the customer/quote **with those exact ids** — letting CRM record
  `converted_customer_id` / `converted_quote_id` without reading anything back from sales (no
  sales→crm import, no cycle).

## Cross-module boundary (§5 / no cycle, D-057)

CRM is the **top** of the dependency order and reads **downward** only, through the owning module's
`queries.py` (never `service`/`models`, never a cross-module FK):

| Read | Owner | Why |
|---|---|---|
| `currency_exists` | `finance/queries` | a lead/opportunity currency is real |
| `employee_exists` | `hr/queries` | `owner_employee_id` is a real employee |
| `item_exists`, `get_base_uom` | `inventory/queries` | an opportunity line's item is real + its base UoM for the quote line |
| `customer_exists`, `get_customer` | `sales/queries` | an opportunity's existing `customer_id` is real |

The **only** import in the other direction is **sales → `crm/events`** (the typed event class) +
**`crm/constants`** (the declarative `converted_to_quote` link string) — the sanctioned **events-only /
declarative** allowance (STRUCTURE §5 / D-011), the same pattern every cross-module handler uses (e.g.
finance importing `sales/constants`/`sales/events`). finance/inventory/hr/sales are **older** modules
that import **nothing** from crm, and sales needs nothing back from crm (CRM pre-generated the ids), so
crm→{…}/queries is one-directional and crm←sales/events is events-only → **no cycle**.

## Permissions (D-009)

`crm.lead.read/.manage`, `crm.opportunity.read/.manage`, **`crm.opportunity.convert`** (the distinct
convert action — converting a won deal into a real customer + quote is higher-privilege than editing),
`crm.activity.read/.manage`.

## Out of v1 (recorded in the parity doc)

Campaigns & marketing automation; contact/account (business-partner) hierarchies; forecasting &
pipeline analytics; service tickets/cases; opportunity teams, competitors, products-with-price-books;
lead scoring/assignment rules; email/calendar integration. The convert's quote is a standard sales
quote — opportunity-specific pricing/discount conditions are a sales concern, not CRM's.

## Files

`constants.py` (enums + permissions + numbering + the convert link/event keys), `models.py` (the four
tables), `schemas.py`, `queries.py` (the only file another module could import), `service/`
(`leads` / `opportunities` / `activities` / `convert` + `_shared`), `events.py`
(`OpportunityConverted`), `router.py` + `opportunity_router.py` + `activity_router.py` (one surface at
`/api/v1/crm`). The convert handler lives in **`sales/handlers.py`** (sales owns the customer/quote
write). Migration **`0042_crm`** (down_revision 0041; four tables, no trigger-bearing alters,
reversible + zero drift on both engines).
