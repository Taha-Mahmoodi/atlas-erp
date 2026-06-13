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

## Tables (migrations 0028 + 0029)

| Table | Migration | Purpose |
|---|---|---|
| `sales_customer_groups` | 0028 | Lean grouping master (tenant, `code`, `name`) that pricing keys on. |
| `sales_customers` | 0028 | The customer master. Its `id` **IS** finance AR's opaque `partner_id`. |
| `sales_price_lists` | 0028 | Condition headers: currency + optional group + date window + priority + status. |
| `sales_price_list_items` | 0028 | One base `unit_price` per (list, item), with an optional `min_quantity` floor. |
| `sales_quotes` / `sales_quote_lines` | 0029 | The pre-sales quotation (DocumentMixin, `QUO-` number) + its lines (opaque item/uom, discount). |
| `sales_orders` / `sales_order_lines` | 0029 | The committing order (DocumentMixin, `SO-` number, `source_quote_id`, `credit_check_status`) + its lines (ordered/delivered/invoiced quantities). |

All carry the D-007 composite-tenant-FK backstop (`tenant_unique()` + `tenant_fk()`); money/quantity
columns use `MoneyType`/`QuantityType` (D-015, exact on both engines). Both migrations create tables
and indexes only — no triggers, no alters.

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
| `POST /quotes`, `GET /quotes`, `GET/PATCH /quotes/{id}` | `sales.quote.read` / `.manage` | Quote CRUD; create idempotent; list paginated, `?status=&customer_id=`. |
| `POST /quotes/{id}/send,/accept,/reject,/cancel` | `sales.quote.manage` | Lifecycle actions; send/accept/reject idempotent. |
| `POST /quotes/{id}/convert-to-order` | `sales.order.manage` | Raise an order from an ACCEPTED quote (idempotent). |
| `POST /orders`, `GET /orders`, `GET/PATCH /orders/{id}` | `sales.order.read` / `.manage` | Order CRUD; create idempotent; list paginated, `?status=&customer_id=`. |
| `POST /orders/{id}/confirm` | `sales.order.confirm` | The ATP + credit gate (idempotent). Returns CONFIRMED or CREDIT_BLOCKED (not an error). |
| `POST /orders/{id}/credit-release` | `sales.order.credit_release` | Release a CREDIT_BLOCKED order past the limit, then confirm (idempotent). |
| `POST /orders/{id}/cancel` | `sales.order.manage` | Cancel before any delivery/invoice. |
| `POST /orders/atp` `{lines:[{item_id,quantity}]}` / `GET /orders/atp?item_id=&quantity=&date=` | `sales.order.read` | The availability preview (D-044). |

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

7.1 publishes **no domain events** (masters + pricing drive no cross-module effects). **7.2 still
publishes none:** a confirmed order is a COMMITMENT (like a PO) with no finance/inventory posting —
7.3's delivery is the first sales event (stock issue → COGS). So there is no `events.py`/`handlers.py`
under sales yet (the no-empty-file rule).

## Quote → Order (7.2, D-044)

The O2C spine mirrors the procurement requisition/PO chain. Both documents are numbered at creation
(D-012/D-040): `QUO-2026-NNNNN` and `SO-2026-NNNNN`.

**Quote lifecycle** (`QuoteStatus`): DRAFT → SENT → ACCEPTED/REJECTED; DRAFT/SENT → EXPIRED on
`valid_until` lapse (a lazy check the read paths run, no background sweep); ACCEPTED → CONVERTED when
an order is raised; CANCELLED before conversion. Lines default `unit_price` from
`sales/queries.resolve_price` (overridable) and apply an optional per-line discount (`DiscountType`
PERCENT/AMOUNT); `line_amount` = qty × unit_price − discount, `total_amount` is the maintained sum.

**Order lifecycle** (`SalesOrderStatus`): DRAFT → (confirm) CONFIRMED or CREDIT_BLOCKED, + CANCELLED
(set in 7.2); PARTIALLY_DELIVERED/DELIVERED (7.3), INVOICED (7.4), CLOSED (the full lifecycle declared
now). An order is created from scratch OR by converting an ACCEPTED quote (copy lines + frozen prices,
link docflow `converted_to`, set `source_quote_id`, advance the quote to CONVERTED). The customer must
be ACTIVE at create (422 `sales.customer_not_active` — the soft block, distinct from the credit
block). `payment_terms_days` is snapshot from the customer.

### ATP — availability check, backorder flag, NOT a block (D-044)

`atp_check(item_id, qty, date)` computes **availability = on-hand − committed + on-order**:

- **on-hand** = `inventory/queries.total_on_hand` (the maintained quant projection);
- **committed** = `committed_quantity` — the undelivered demand (ordered − delivered) of
  CONFIRMED/PARTIALLY_DELIVERED sales orders for the item (a set-based scan, no N+1). This is the
  **reservation**: confirming an order commits its undelivered quantity against ATP for the next
  order. Confirm excludes the order's own demand so it is checked net of *other* commitments.
- **on-order** = `procurement/queries.open_incoming_quantity` — ordered − received summed over
  APPROVED/SENT/PARTIALLY_RECEIVED POs (a sanctioned cross-module read added in 7.2).

A line whose requested quantity exceeds availability is a **backorder** — but ATP is **informational**:
parity scopes v1 to "simple ATP = an availability check with manual backorders", so confirm records
which lines are backordered (the ATP snapshot) and **proceeds** (the order still CONFIRMS). The hard
block is credit.

### Credit — the HARD block at confirmation (D-044)

Exposure = the customer's **open AR** (`customer_open_ar` → finance's `customer_open_balance`, the
sum of `open_amount` on POSTED customer invoices keyed by the opaque partner_id) + the value of the
customer's **other open confirmed orders** (`open_confirmed_order_value`) + **this order's total**. If
exposure > the customer's `credit_limit` (0 = cash-only) the order is set **CREDIT_BLOCKED** /
`credit_check_status` BLOCKED and is **NOT confirmed** — the static credit-limit block parity scopes
to v1. Within the limit → **CONFIRMED** / PASSED. A user with `sales.order.credit_release` calls
**release_credit**, which sets `credit_check_status` RELEASED and re-confirms (a RELEASED order skips
the credit gate). `confirm` distinct from `manage` because it runs the gates; `credit_release` distinct
because it is an approval-like override. Confirm is idempotent (re-confirming a CONFIRMED order is a
no-op).

### Reservation model (committed quantity)

A CONFIRMED order's undelivered quantity (ordered − delivered) is "committed" — there is no separate
reservation table; `committed_quantity` is a query over confirmed-but-undelivered order lines (D-044).
When 7.3 delivers, `delivered_quantity` rises and the commitment shrinks automatically.

## What 7.3–7.4 add

- **7.3** Delivery with partial shipments + backorders → stock issue + COGS via the event bus (the
  first sales event). `delivered_quantity` rises; the order advances PARTIALLY_DELIVERED/DELIVERED.
- **7.4** Billing: customer invoice from delivery (revenue journals, `tax_code_id` per line), RMA
  returns with credit notes. `invoiced_quantity` rises; the order advances INVOICED/CLOSED.

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
