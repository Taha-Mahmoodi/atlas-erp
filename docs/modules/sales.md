# Sales module

The fourth business module (PLAN 7), opening the order-to-cash side. PLAN **7.1** delivers the
**customer master** and the **condition-style pricing engine**; the quote → order → delivery →
invoice chain (7.2–7.4) builds on top. Sales sits above inventory and finance in the dependency
order (STRUCTURE §5): it reads `finance/queries` + `inventory/queries` downward, and everyone above
it reads `sales/queries`.

Parity (`docs/research/s4hana-parity.md`, Sales section): the customer master is **PARTIAL** (core
sales data, not the multi-role business-partner model) and pricing is **PARTIAL** (condition-style
price lists by currency / customer group / date range + discounts, NOT the generalized
access-sequence engine). What 7.1 deliberately omits is listed under *Deferred* below.

## Tables (migration 0028)

| Table | Purpose |
|---|---|
| `sales_customer_groups` | Lean grouping master (tenant, `code`, `name`) that pricing keys on. |
| `sales_customers` | The customer master. Its `id` **IS** finance AR's opaque `partner_id`. |
| `sales_price_lists` | Condition headers: currency + optional group + date window + priority + status. |
| `sales_price_list_items` | One base `unit_price` per (list, item), with an optional `min_quantity` floor. |

All four carry the D-007 composite-tenant-FK backstop (`tenant_unique()` + `tenant_fk()`); money/
quantity columns use `MoneyType`/`QuantityType` (D-015, exact on both engines). The migration creates
tables and indexes only — no triggers, no alters.

## The customer ↔ AR `partner_id` relationship (D-029)

Finance is the bottom of the dependency order and owns **no** customer table. Every AR document
(`fin_customer_invoices`, customer receipts) stores its customer as an **opaque `partner_id`** (a
plain `Uuid`, no FK) plus a denormalized `partner_name`. **That `partner_id` is exactly
`Customer.id`.** Sales is above finance, so finance can never FK-reference the customer master; the
link is resolved the other way, through `sales/queries.get_customer_for_partner(session, tenant_id,
partner_id)` — a thin, intent-named alias over `get_customer`. This is the exact mirror of the
procurement vendor ↔ AP `partner_id` link.

## Credit-limit semantics (D-043)

`Customer.credit_limit` is a **non-null `MoneyType` defaulting to 0** meaning the **maximum
outstanding AR** (open invoices) the customer may carry:

- **`0` (default) → cash-only.** No open credit at all; 7.2's order confirmation blocks if confirming
  would leave any positive outstanding AR. New customers are cash-only until a limit is set.
- **a positive value → the credit ceiling.** 7.2 blocks confirmation when outstanding AR + the new
  order would exceed it.

There is **no NULL/"unlimited" sentinel** in v1: "unlimited" is expressed by an explicit large limit,
keeping the column non-null and 7.2's check a single unconditional comparison with no NULL branch. A
DB `CHECK (credit_limit >= 0)` backs it. This is the **static** credit-limit block the parity doc
scopes to v1 — no exposure aggregation across open orders/deliveries, no finance-owned exposure
ledger (a documented later). `sales/queries.customer_credit_limit` exposes it to 7.2.

## Customer groups

A customer optionally belongs to **one** `CustomerGroup`. A master table (not a free-string column)
was chosen because **pricing keys on the group**: a `PriceList` targets a group by id (a composite
tenant FK), so the customer and the price list reference the same group rows, the group name is
edited in one place, and a typo'd free-string group can never silently exclude a customer from its
price list. The group carries no pricing of its own — it is purely a grouping key. `customer_group_id`
is nullable on both the customer and the price list (NULL on a price list = a **general** list).

## The price-list condition model + deterministic resolution (D-043)

A `PriceList` is a **condition header**: a `currency_code`, an optional `customer_group_id` (NULL =
general), an inclusive `[valid_from, valid_to]` window (`valid_to` NULL = open-ended), a `status`
(ACTIVE/INACTIVE), and a `priority` integer. Each list carries `PriceListItem` rows — **one base
`unit_price` per item**, with a `min_quantity` floor (default 0; v1's only scale knob).

`resolve_price(item, customer, on_date, quantity, currency)` (in `service/price_resolution.py`,
exposed via `sales/queries.resolve_price`) returns the applicable base price. A price list **applies**
when **all** of:

1. `status == ACTIVE`;
2. `currency_code == currency`;
3. `valid_from <= on_date` and (`valid_to IS NULL` or `valid_to >= on_date`);
4. the list is **general** (`customer_group_id IS NULL`) **or** targets the customer's group;
5. it has a `PriceListItem` for the item whose `min_quantity <= quantity`.

Among the applying lists the winner is picked by, in **strict order**:

1. **highest `priority`** (the explicit tenant override);
2. then **most specific** — a group-targeted list beats a general (null-group) list;
3. then **latest `valid_from`** — a newer campaign price supersedes an older one;
4. then **price-list `id`** as a final stable tiebreaker (so the result never depends on row order).

If nothing applies, the resolver returns `matched=False` (no price) — 7.2's order entry then requires
a manual price or an override. **No discount is applied here**: the price list yields the *base price
only*; line discounts (`DiscountType` PERCENT/AMOUNT) are a per-order-line concern in 7.2.

The resolver is **bounded to two queries** regardless of how many lists exist (PERFORMANCE §6): one
fetches the small candidate set of ACTIVE lists matching currency + date + group (index-served by
`ix_sales_price_lists_resolver`), one fetches those lists' items for this item meeting the quantity
floor; the winner is picked in Python over that small set — no per-list N+1.

## API (`/api/v1/sales`)

| Method + path | Permission | Notes |
|---|---|---|
| `GET /customers` | `sales.customer.read` | Paginated, `?status=` filter, collection ETag. |
| `POST /customers` | `sales.customer.manage` | |
| `GET/PATCH /customers/{id}` | read / manage | `customer_code` immutable. |
| `GET /customer-groups` | `sales.customer.read` | Paginated, collection ETag. |
| `POST /customer-groups`, `GET/PATCH /customer-groups/{id}` | read / manage | `code` immutable. |
| `GET /price-lists` | `sales.pricelist.read` | Paginated, `?status=` filter, collection ETag. |
| `POST /price-lists`, `GET/PATCH /price-lists/{id}` | read / manage | `code` immutable. |
| `GET /price-lists/{id}/items` | `sales.pricelist.read` | The nested price rows. |
| `POST /price-lists/{id}/items`, `DELETE …/items/{item_id}` | manage | Item validated via inventory. |
| `GET /price-quote?item_id=&customer_id=&quantity=&date=` | `sales.pricelist.read` | Resolved price (D-043); `date` defaults to today; currency = the customer's default. |

Reference lists (customers, customer groups, price lists) support conditional GETs via a tenant-scoped
collection ETag (PERFORMANCE §3 / D-035): an `If-None-Match` hit returns 304 without running the page
query. Every list runs within the ≤3-query budget (auth load + page select).

## Cross-module contracts

- **Downward reads:** `finance/queries.currency_exists` (validate a customer/price-list currency);
  `inventory/queries.item_exists` (validate a price-list item). Never a cross-module FK (D-029).
- **`sales/queries` (the only file other modules import):** `get_customer`,
  `get_customer_for_partner`, `customer_exists`, `customer_status`, `customer_credit_limit`,
  `customer_payment_terms_days`, `customer_default_currency`, and `resolve_price`. 7.2–7.4 and finance
  AR reporting read these.

7.1 publishes **no domain events** (masters + pricing drive no cross-module effects); the order flow
in 7.2 will.

## What 7.2–7.4 add

- **7.2** Quote → Order with a simple ATP check (on-hand + on-order) and the **credit-limit block** at
  confirmation (reads `customer_credit_limit` + outstanding AR), plus per-line discounts
  (`DiscountType`) on top of the resolved base price. Order entry prices each line through
  `sales/queries.resolve_price`.
- **7.3** Delivery with partial shipments + backorders → stock issue + COGS via the event bus.
- **7.4** Billing: customer invoice from delivery (revenue journals), RMA returns with credit notes.

## Deferred (per parity)

- The multi-role **business-partner** model (distinct ship-to/payer/bill-to per document) — v1 keeps a
  single customer record.
- The generalized **access-sequence / pricing-procedure** engine, multi-tier **quantity scales**
  (several prices per item with their own breaks), freight/tax condition types, and price-approval
  workflows — v1 keeps one base price per (list, item) with a single `min_quantity` floor.
- **Exposure-based credit management** (aggregation across open orders/deliveries/receivables, rechecks
  at delivery, a release workbench) — v1 has only the static credit-limit block.
- Sales **contracts / scheduling agreements**, **output management**, **rebates**, and
  **intercompany / third-party (drop-ship)** flows — out of scope for v1.
