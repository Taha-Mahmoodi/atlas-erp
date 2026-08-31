# Finance (`backend/app/modules/finance/`)

Finance is the first business module and the **bottom of the dependency order** (STRUCTURE §5):
every other module may read `finance/queries.py`, and finance imports no other module. The
full normative design lives in [docs/architecture.md](../architecture.md) (D-017…D-022); this
guide is the operator/contributor map, and it grows with each finance task (PLAN 4.1…4.10).

## Status

PLAN 4.1 laid the **schema foundation**: the chart of accounts and fiscal years/periods.
PLAN 4.2 added the **universal journal** (D-017) — the heart of the system — and the **four
DB-level guard triggers** (D-018/D-017). PLAN 4.3 added **multi-currency** (D-019): currencies +
rates, posting-time translation, unrealized-FX revaluation. PLAN 4.4 added the **tax engine**:
configurable line-level tax codes + the calculation service AP/AR/Sales call. PLAN 4.5/4.6 added
**Accounts Payable** and **Accounts Receivable** (D-029, opaque `partner_id`): bills, payments,
invoices, receipts, open-item clearing with realized FX, dunning and aging. PLAN 4.7 added
**Controlling**: cost/profit centres as journal dimensions + allocation rules and runs. PLAN 4.8
added the **financial statements** (D-021) — trial balance, P&L, balance sheet, indirect
cash flow, cost-centre report and margin-by-product — all as pure projections of ONE base aggregate
over `fin_journal_lines`, with no stored totals anywhere. PLAN 4.9 added **bank
reconciliation**: CSV statement import (background job above 1k lines, PERFORMANCE §3), match
suggestions against posted journal lines, and clearing postings for bank-only lines.
PLAN 4.10 (this task — **completes Phase 4**) adds **asset accounting lite**: the asset
register, straight-line + declining-balance depreciation runs posting ONE grouped journal
entry each, and the register-as-projection report.

| File | Concern | Key decision |
|---|---|---|
| `constants/` (`enums.py`, `documents.py`, `permissions.py`) | every finance StrEnum + normal-balance mapping; doc types, sequences, link types, posting purposes, job keys; permission keys — split into a package at the 400-line cap (STRUCTURE §8.4), fully re-exported from `__init__` so every existing import is unchanged | D-021, D-018, D-017, D-019, D-009 |
| `models/accounts.py` | `Account` (+ `is_monetary`/`currency_code`), `AccountGroup`, `FiscalYear`, `FiscalPeriod` | D-021, D-018, D-019 |
| `models/journal.py` | `JournalEntry`, `JournalLine` (the universal journal) | D-017, D-021 |
| `models/fx.py` | `Currency`, `ExchangeRate`, `PostingDefault`, `FxRevaluationRun` | D-019 |
| `models/tax.py` | `TaxCode` (configurable line-level tax codes) | PLAN 4.4 |
| `models/controlling.py` | `CostCenter`, `ProfitCenter`, `AllocationRule`, `AllocationRuleTarget`, `AllocationRun` | PLAN 4.7, D-021 |
| `models/bank.py` | `BankStatement`, `BankStatementLine` (imported statements for reconciliation) | PLAN 4.9, D-012 |
| `models/assets.py` | `Asset`, `DepreciationRun`, `DepreciationEntry` (UNIQUE(asset, period) idempotency backbone) | PLAN 4.10, D-012 |
| `schemas.py` | Create/Update/Read/Filter for accounts, periods, journal, **FX**, **tax** | — |
| `service/accounts.py` | chart-of-accounts business logic | D-021 |
| `service/periods.py` | fiscal years/periods + open/close lifecycle | D-018 |
| `service/journal.py` | draft creation, two-flush posting (+ FX translation), reversal | D-017, D-019 |
| `service/fx.py` | rate lookup, currency mgmt, translation | D-019 |
| `service/fx_translation.py` | posting-time line translation + largest-remainder balancing | D-019 |
| `service/fx_revaluation.py` | unrealized-FX revaluation run + auto-reversal | D-019 |
| `service/posting_defaults.py` | purpose-keyed account wiring (reused by AP/AR/COGS) | D-019 |
| `service/tax.py` | tax calculation (inclusive/exclusive, document grouping) + tax-code CRUD | PLAN 4.4 |
| `service/controlling.py` | cost/profit-centre CRUD + acyclic hierarchy | PLAN 4.7 |
| `service/allocation_rules.py` | allocation-rule + target CRUD + weight validation | PLAN 4.7 |
| `service/allocation.py` | `run_allocation` redistribution engine | PLAN 4.7, D-021 |
| `service/statements/` | the six statement projections + `base._account_balances` (the single aggregate) + shared `grouping` | PLAN 4.8, D-021 |
| `statements_schemas.py` / `statements_router.py` | statement Read schemas + the six read-only GET endpoints | PLAN 4.8 |
| `service/bank_csv.py` | the bank-statement CSV contract: header, row validation, parsing | PLAN 4.9 |
| `service/bank_import.py` | statement import (bulk line insert), the import job handler, progress/status derivation, reads | PLAN 4.9, PERF §2/§3 |
| `service/bank_reconcile.py` | match suggestions (two rules), confirm/reject, clearing postings | PLAN 4.9 |
| `bank_schemas.py` / `bank_router.py` | bank-reconciliation schemas + endpoints (201/202 import split) | PLAN 4.9, D-013 |
| `service/assets.py` | asset register lifecycle: create/update DRAFT, activate (+ acquisition posting) | PLAN 4.10, D-012 |
| `service/depreciation.py` | `compute_depreciation` (the two formulas) + the set-based posting run + the run job handler | PLAN 4.10, PERF §2/§3 |
| `service/depreciation_read.py` | run/entry reads + the asset-register projection | PLAN 4.10, D-021 |
| `assets_schemas.py` / `assets_router.py` | asset-accounting schemas + endpoints (201/202 run split) | PLAN 4.10, D-013 |
| `events.py` | `JournalEntryPosted`, `JournalEntryReversed`, `AllocationPosted` | D-011 |
| `queries.py` | the cross-module read interface finance **exposes** (+ `get_rate`, `get_tax_code`, `cost_center_balance`, `cost_center_exists`, `profit_center_exists`) | STRUCTURE §5 |
| `router.py` / `fx_router.py` / `tax_router.py` / `ap_router.py` / `ar_router.py` / `co_router.py` / `bank_router.py` / `assets_router.py` | thin HTTP layer at `/api/v1/finance` | D-013 (idempotent post/reverse/revalue/run/import/clear/activate) |

> Money/quantity/rate exactness comes from `core/money.py` (D-015): `MoneyType`/`QuantityType`
> store NUMERIC on Postgres and INTEGER scaled minor units on SQLite, so the balance trigger's
> SUM and the one-side CHECK are exact on **both** engines; `allocate()` is the largest-remainder
> splitter (FX residual-cent, tax/discount splits).

## The chart of accounts — why statements become derivable (D-021)

Atlas follows the S/4HANA "universal journal" rule: every financial statement is a **projection**
of journal lines, never a separately-stored total. For that to work, each account carries the
minimal metadata from which all four statements derive mechanically:

- **`account_type`** — one of `ASSET`, `LIABILITY`, `EQUITY`, `REVENUE`, `EXPENSE`. This single
  field drives every statement: the trial balance groups by account; the P&L sums
  `REVENUE` + `EXPENSE` over a range; the balance sheet takes `ASSET` / `LIABILITY` / `EQUITY`
  cumulative to a date (with retained earnings computed on the fly from `REVENUE` + `EXPENSE`
  net over all history).
- **`normal_balance`** (`DEBIT` / `CREDIT`) — derivable from the type (`ASSET`/`EXPENSE` → `DEBIT`;
  `LIABILITY`/`EQUITY`/`REVENUE` → `CREDIT`) but **stored** for query simplicity. The service
  defaults it from the type when a caller omits it, so the stored side can never disagree with
  the type.
- **`cash_flow_category`** (`OPERATING` / `INVESTING` / `FINANCING`, nullable) and
  **`is_cash_equivalent`** — feed the indirect cash-flow statement.
- **`is_postable`** — only leaf/postable accounts accept journal lines; presentation roll-up
  accounts carry no postings. The journal posting service (4.2) enforces this on every line.

The **account-group tree** (`fin_account_groups`, self-referential `parent_id`) is a **pure
presentation hierarchy** — it carries no postings and no balances; accounts hang off a group via
`account_group_id`. Because the hierarchy lives entirely on the group tree, accounts themselves
have no `parent_id`. The service guards the tree against cycles (a group can never be its own
ancestor) when a group is reparented.

The account-type model implemented here is **exactly** what the statement projections in 4.x
consume — no statement code needs anything beyond these fields.

## Fiscal periods and the close lifecycle (D-018)

A **`FiscalYear`** owns N **`FiscalPeriod`** rows. Creating a year auto-generates `period_count`
(default 12) **contiguous, non-overlapping monthly periods**: each period runs from its start to
the day before the next period's start, so the periods exactly tile the year — and the year's
`end_date` is set to the last period's end. Month lengths are handled correctly (a January 31st
start clamps February to the 28th/29th).

Every period and year starts `OPEN`. The lifecycle:

- **`close_period`** sets a period `CLOSED`; **`open_period`** reopens it (refused if the period's
  year is already `CLOSED`).
- **`close_fiscal_year`** is allowed only once **every** one of its periods is `CLOSED` — a closed
  year asserts the whole year is settled.

A `CLOSED` period rejects postings dated within it. The **date → period lookup** the journal uses
on every posting is backed by the `(tenant_id, start_date, end_date)` index and exposed as
`queries.find_period_for_date`.

### The close-time invariant (D-018, now enforced)

D-018 mandates period-close enforcement at **both** the service and DB level.

- **`service/periods.assert_period_closable(...)`** now refuses closing a period that is already
  closed **or** that still holds `DRAFT` journal entries dated within it (a draft in a closed
  period would become unpostable). Posted/reversed entries are immutable settled facts and never
  block a close.
- The **DB-level period-posting trigger** `trg_fin_journal_entries_period_open_*` fires on
  `fin_journal_entries` (migration `0009`) on a direct posted INSERT and on the DRAFT→POSTED
  UPDATE; it **re-derives** the open period from `NEW.posting_date` by date, so a wrong
  `fiscal_period_id` can never smuggle a posting into a closed period. It raises
  `ATLAS_PERIOD_CLOSED` → `finance.period_closed` (422).

## The universal journal (D-017)

One append-only line table (`fin_journal_lines`) is the single source of truth for every FI/CO
view (D-021); `fin_journal_entries` is the header carrying entry-level lifecycle. An entry is
**single-transaction-currency**. For v1 functional amounts **equal** transaction amounts (single
functional currency; posting-time FX translation lands in 4.3).

**Lifecycle:** `DRAFT` → `POSTED` → `REVERSED`. A posted entry is **immutable**; the only
correction is a reversing entry (CLAUDE.md rule 8). Numbers (`JE-YYYY-#####`) are **gapless** and
claimed at **posting**, never at draft creation (D-012), so an abandoned draft burns no number.

### Posting protocol — two flushes (D-017)

`service/journal.post_entry` is deliberately two-flush because the unit of work does not guarantee
cross-table UPDATE order:

1. Validate the entry is `DRAFT`, has ≥2 one-sided lines that balance, and that `posting_date`
   falls in an **open** period (422 `finance.period_closed` before touching the DB).
2. Claim the gapless `entry_number` in **this** transaction.
3. **Flush 1** — set each *loaded* line's `is_posted`/`posting_date`/`fiscal_period_id` while the
   entry is still `DRAFT` (the line-immutability trigger keys on `OLD.is_posted = FALSE`, so the
   posting flush is allowed).
4. **Flush 2** — set the header `POSTED`/`posted_at`/`fiscal_period_id` (the period + balance
   triggers fire on this DRAFT→POSTED UPDATE).
5. Publish `JournalEntryPosted`; commit via `run_in_uow`.

Lines are mutated as **loaded objects** (never bulk `update()`) so the audit diffs are captured
and the audit bulk-write assertion is respected. The denormalized line fields make every
statement projection a header-join-free query over `fin_journal_lines` (D-021).

### Reversal-only correction (D-017)

`service/journal.reverse_entry` loads a `POSTED` entry, creates a **new** entry of the same
`document_type` with each line's debit/credit **swapped** in both currency pairs, posts it (its
own number), then sets the original `REVERSED` + `reversed_by_entry_id` — the **only** mutation
the immutability trigger permits on a posted header. The two documents are linked in docflow with
link type `reverses`. No deletes, no in-place edits, ever.

### The four DB-guard triggers (migration 0009, both dialects)

| Trigger | Table / event | Raises | Enforces |
|---|---|---|---|
| `trg_fin_journal_entries_period_open_ins` / `_upd` | entries, BEFORE INSERT / UPDATE (DRAFT→POSTED) | `ATLAS_PERIOD_CLOSED` | posting only into an open period covering `posting_date` (D-018) |
| `trg_fin_journal_entries_balanced` | entries, BEFORE UPDATE (DRAFT→POSTED) | `ATLAS_UNBALANCED_ENTRY` | Σ functional debit = Σ functional credit > 0 over the lines (D-017) |
| `trg_fin_journal_entries_immutable` / `_no_delete` | entries, BEFORE UPDATE / DELETE on a POSTED header | `ATLAS_POSTED_IMMUTABLE` | a posted entry is immutable except the sanctioned POSTED→REVERSED transition (D-017) |
| `trg_fin_journal_lines_immutable` / `_no_delete` | lines, BEFORE UPDATE / DELETE where `OLD.is_posted` | `ATLAS_POSTED_IMMUTABLE` | a posted line is frozen; the posting flush (FALSE→TRUE) is allowed (D-017) |

Plus the column CHECK `ck_fin_journal_lines_one_side` (debit XOR credit per line). The triggers
are written per-dialect (plpgsql on Postgres, `RAISE(ABORT)` on SQLite) and proven firing on
**both** engines by `tests/modules/finance/test_journal_db_guards.py` (raw-SQL bypass, the default
SQLite run + the `-m pg` Postgres run). Tokens are translated to the error envelope by
`core/exceptions.py` (`finance.period_closed`/`finance.journal_unbalanced`/`finance.entry_immutable`,
all 422).

## Multi-currency (D-019)

PLAN 4.3 adds transaction + functional currency with a rates table, posting-time translation, and
an unrealized-FX revaluation run. One **functional currency** per tenant (the books' reporting
currency); every other currency is foreign. Multi-currency is **opt-in**: a tenant with no
functional currency configured behaves exactly as before (functional == transaction).

### Currencies and rates

- `fin_currencies` — the tenant currency catalog. Exactly **one** row has `is_functional` (enforced
  by the service and by a partial unique index on `(tenant_id) WHERE is_functional` on both
  engines). `decimal_places` drives posting rounding (USD=2, JPY=0, BHD=3).
- `fin_exchange_rates` — a `rate` for a `(rate_date, from, to, rate_type)` tuple; `rate_type` is
  `SPOT` (posting) or `CLOSING` (revaluation); `rate` is `RateType` (full 10-dp precision, never
  quantized).
- **`get_rate(session, tenant, from, to, on_date, rate_type=SPOT)`** returns the most recent rate
  with `rate_date <= on_date` for the **direct** pair; `from == to` → 1; if only the **inverse**
  pair is stored, `1 / inverse_rate` rounded to 10 dp (direct-or-inverse, never triangulated); a
  missing rate raises `finance.exchange_rate_missing` (422) — **postings never guess**.

### Posting-time translation with frozen functional amounts

Translation happens **exactly once, at posting** (`service/fx_translation.translate_entry_lines`,
called by `post_entry`). When the entry currency differs from the functional currency, each line's
functional debit/credit becomes `quantize(transaction_amount × rate, functional_decimals)` HALF_UP
at the SPOT rate for `posting_date`. Quantizing each line independently can leave the functional
debit total a cent off the credit total — the balance trigger SUM-checks the **functional** amounts
— so the residual is absorbed into the largest line via `core/money.allocate` (largest-remainder),
**not** a separate rounding line (a functional-only line would violate the one-side CHECK, D-017).
A caller may pass an explicit `rate_override` to `post_entry`, which wins over the looked-up rate
(no header column is added, so `fin_journal_entries` and its four triggers are never altered).
Posted lines are **never re-translated** (immutability triggers guarantee it); a reversal copies the
original's frozen functional amounts swapped, also without re-translation.

### Posting defaults (data-driven account wiring)

`fin_posting_defaults` maps a **purpose** string to a GL account, so FX (and later AP/AR/COGS) post
to configured accounts rather than hard-coded codes. `get_posting_default` raises
`finance.posting_default_unmapped` (422) when a needed purpose is unset. FX purposes:
`fx_realized_gain`, `fx_realized_loss`, `fx_unrealized_gain`, `fx_unrealized_loss`,
`fx_revaluation_adjustment`.

### Unrealized FX revaluation + auto-reversal

`run_fx_revaluation(session, tenant, period_id, rate_date)`:

1. Resolves the functional currency and **validates the next period exists and is OPEN up front**
   (the auto-reversal posts there) — a clear `finance.fx_reval_next_period_not_open` (422) **before
   any entry posts**.
2. If a prior **COMPLETED** run exists for the period, reverses its entries first (append-only,
   never delete) and marks the run `REVERSED`.
3. For each account flagged **`is_monetary`** with a foreign `currency_code` and a non-zero foreign
   balance as of `rate_date`: `delta = quantize(foreign_balance × CLOSING_rate, dp) − functional
   carrying`. Posts one balanced **`FX_REVAL`** entry (adjustment account vs
   `fx_unrealized_gain`/`fx_unrealized_loss`) plus its **auto-reversal dated day 1 of the next
   period**, linked by a `revalues` docflow edge.
4. Records the run `COMPLETED` in `fin_fx_revaluation_runs`.

**Scope (v1):** the per-account monetary foreign balance — accounts marked `is_monetary` with a
non-functional `currency_code`. Per-open-item AP/AR revaluation granularity is **bounded out of
v1** (it needs the AP/AR open-item model, PLAN 4.4+) and is recorded as 'partial' in the parity
doc; it reuses exactly this rates-table + FX-account machinery when it lands. **Realized FX** (at
open-item clearing) is likewise deferred to AP/AR — the `fx_realized_gain`/`fx_realized_loss`
purposes are wired now for that consumer.

## The tax engine (PLAN 4.4)

Tax is configured as a catalog of **tax codes** (`fin_tax_codes`) and applied **at the line level**:
a document line references a tax code, and the calculation service (`service/tax.py`) turns the
line's base amount into net / tax / gross plus the GL account the tax posts to. AP (4.5), AR (4.6)
and Sales all call this one engine through `queries.py`, so tax math is computed identically
everywhere — finance is the bottom of the dependency order (STRUCTURE §5).

### Tax codes

A `TaxCode` carries `code` (e.g. `VAT20`), `name`, `rate_percent` (a **percentage** — `20` means
20% — stored exactly via `MoneyType`, D-015, **not** a money amount), `jurisdiction` (e.g. `GB`),
`is_inclusive`, `is_active`, and two **nullable** posting accounts:

- `tax_payable_account_id` — collects **OUTPUT** (sales/AR) tax, a **liability** owed to the
  authority;
- `tax_receivable_account_id` — collects **INPUT** (purchase/AP) tax, **recoverable** from the
  authority.

Each is optional so a code wires only the side it serves. The calc service picks the account by
`TaxDirection` (`OUTPUT` for sales, `INPUT` for purchase) and raises a clear 422 when the needed
side is unwired. `UNIQUE(tenant_id, code)` keys the code per tenant; both account links are
composite tenant FKs (D-007). `code` is immutable after creation (a posted line references it).

### Inclusive vs exclusive math (ROUND_HALF_UP, D-015)

Both modes quantize every amount HALF_UP to the currency's minor unit:

- **Exclusive** — the line base **is the net**; tax is added on top:
  `tax = round(net × rate)`, `gross = net + tax`. Net 100 @ 20% → tax 20, gross 120.
- **Inclusive** — the line base **is the gross** (tax already inside the price):
  `net = round(gross ÷ (1 + rate))`, `tax = gross − net`. Gross 120 @ 20% → net 100, tax 20.
  Deriving tax as `gross − net` (not `gross × rate ÷ (1+rate)` directly) keeps `net + tax == gross`
  exactly after rounding — the two rounded parts always reconstitute the rounded gross. On an
  awkward rate (e.g. 19.6%) the HALF_UP rounding lands the cent deterministically.

### Calculation API

- `calculate_line_tax(base_amount, tax_code, *, direction, currency_code='USD') -> TaxCalculation`
  — one line. `TaxCalculation` is `(tax_code, direction, net_amount, tax_amount, gross_amount,
  tax_account_id)`.
- `calculate_document_tax(lines, *, currency_code='USD') -> DocumentTaxSummary` — a whole document.
  Lines are `(base_amount, tax_code, direction)`; the result groups by `(code, direction)` into **one
  tax line per code** (`TaxLine`) plus `net_total` / `tax_total` / `gross_total`. The grouped tax is
  the group's **net taxed once** (not the drifting sum of per-line rounded tax), and `allocate`
  (D-015 largest-remainder) confirms the split reconstitutes exactly — so a document's posted tax
  per code is exact to the cent.

**Where AP/AR/Sales plug in:** each builds its journal from the summary — the per-line **net** feeds
the expense/revenue lines, each `TaxLine.tax_amount` posts to its `tax_account_id` (payable for
sales, receivable for purchases), and the **gross** feeds the AP/AR control account. Finance owns the
tax codes and the math; the document modules own the posting.

## The `queries.py` contract (what other modules read)

Finance exposes a thin, stable read surface (STRUCTURE §5 — everyone may import these):

- `find_period_for_date(session, tenant_id, on_date) -> FiscalPeriod | None`
- `get_period_status(session, tenant_id, on_date) -> PeriodStatus | None`
- `account_exists(session, tenant_id, code) -> bool`
- `get_rate(session, tenant_id, from, to, on_date, rate_type=SPOT) -> Decimal` (D-019)
- `functional_currency(session, tenant_id) -> str` (D-019)
- `get_tax_code(session, tenant_id, code) -> TaxCode | None` (PLAN 4.4)
- `calculate_line_tax(base_amount, tax_code, *, direction, currency_code='USD') -> TaxCalculation`
  (PLAN 4.4)
- `get_open_vendor_bills(session, tenant_id, partner_id) -> list[VendorBill]` (PLAN 4.5, D-029)
- `get_open_customer_invoices(session, tenant_id, partner_id) -> list[CustomerInvoice]`
  (PLAN 4.6, D-029)
- `customer_open_balance(session, tenant_id, partner_id) -> Decimal` (PLAN 4.6) — the total still-owed
  AR for a partner across all open invoices; Sales' credit-limit block calls this to ask "how much
  does this customer currently owe?" without importing finance models.

Inventory and sales call `get_period_status` to refuse stock/sales documents dated into a closed
period before they reach the GL; the journal calls `find_period_for_date` to resolve an entry's
period from its posting date; other modules price in functional terms via `get_rate` /
`functional_currency`, and resolve + apply tax via `get_tax_code` / `calculate_line_tax`. AP/AR open
items are keyed by the opaque `partner_id` (D-029) — finance never FK-references a partner master.

## Permissions (D-009)

| Key | Guards |
|---|---|
| `finance.account.read` | read accounts and account groups |
| `finance.account.manage` | create/edit accounts and account groups |
| `finance.period.read` | read fiscal years and periods |
| `finance.period.manage` | create fiscal years, open/close periods |
| `finance.journal.read` | read journal entries and their lines |
| `finance.journal.post` | create draft entries **and** post them |
| `finance.journal.reverse` | reverse posted entries |
| `finance.fx.manage` | manage currencies, exchange rates, posting defaults |
| `finance.fx.revalue` | run foreign-currency revaluation |
| `finance.tax.read` | read the tax-code catalog |
| `finance.tax.manage` | create/edit tax codes |
| `finance.ap.read` | read vendor bills, payments and AP aging |
| `finance.ap.manage` | create and post vendor bills |
| `finance.ap.pay` | create vendor payments and run payment batches |
| `finance.ar.read` | read customer invoices, receipts and AR aging |
| `finance.ar.manage` | create and post customer invoices |
| `finance.ar.collect` | create customer receipts and run dunning |
| `finance.costcenter.read` | read cost centres |
| `finance.costcenter.manage` | create/edit cost centres |
| `finance.profitcenter.read` | read profit centres |
| `finance.profitcenter.manage` | create/edit profit centres |
| `finance.allocation.manage` | create/edit allocation rules |
| `finance.allocation.run` | run cost allocations |
| `finance.statements.read` | read the financial statements (trial balance, P&L, balance sheet, cash flow, cost-centre, margin) |
| `finance.asset.read` | read assets, depreciation runs and the asset register |
| `finance.asset.manage` | create, edit and activate assets |
| `finance.depreciation.run` | run depreciation for a fiscal period (posts a journal) |

One consequence of `finance.fx.manage` guarding `GET /currencies` (#237): the console reads that
list on ~15 screens across 8 modules for one thing only — the CODE it prints next to a money
amount — and none of those personas administer FX. So `useFunctionalCurrency`
(`frontend/src/modules/finance/hooks/reference.ts`) is the one finance hook that sets
`throwOnError: false`: its 403 degrades the label to the same `—` an unconfigured tenant sees
rather than replacing a check, a stock valuation or a maintenance order with a full-page error,
which is what D-067 means by "the record the page is for". `useCurrencyOptions`
(`hooks/settings.ts`) reads the same endpoint and keeps the default, because on the exchange-rate
form the currency list is exactly that record. Widening the endpoint to a `finance.fx.read` is the
alternative fix, and it is not taken: currency rows carry rate-relevant configuration, and adding a
permission key changes every tenant's role data.

## API (`/api/v1/finance`)

- `GET/POST /accounts`, `GET/PATCH /accounts/{id}` — list uses cursor pagination + the `Page`
  envelope; filters (`account_type`, `is_postable`, `is_active`, `account_group_id`) fold into
  the cursor fingerprint.
- `GET/POST /account-groups` — list cursor-paginated (`Page` envelope; #27)
- `GET/POST /fiscal-years` (POST generates the periods), `GET /fiscal-periods` — both lists
  cursor-paginated (`Page` envelope; #27)
- `POST /fiscal-periods/{id}/close` and `/open` — action sub-resources (STRUCTURE §7), guarded by
  `finance.period.manage`.
- `POST /journal-entries` (create draft), `GET /journal-entries` (paginated), `GET /{id}` (with
  lines) — `finance.journal.post` / `finance.journal.read`. The journal endpoints live in
  `journal_router.py` and mount into the finance router (same one-surface pattern as FX/tax),
  keeping `router.py` focused on the COA + fiscal-calendar reference endpoints under the 400-line
  cap.
- `POST /journal-entries/{id}/post` and `/{id}/reverse` — action sub-resources, **idempotent**
  (D-013, require the `Idempotency-Key` header), guarded by `finance.journal.post` /
  `finance.journal.reverse`.
- `GET/POST /currencies`, `GET/POST /exchange-rates`, `GET/PUT /posting-defaults` — all lists
  cursor-paginated (`Page` envelope; #27) — guarded by `finance.fx.manage` (D-019).
- `POST /fx-revaluation-runs` (**background job** since #26: returns `202 {job_id, status}` —
  poll `GET /api/v1/jobs/{job_id}` for the run outcome; **idempotent**, a replayed key returns
  the same job id; guarded by `finance.fx.revalue`), `GET /fx-revaluation-runs` (paginated; #27,
  D-019). The FX endpoints live in `fx_router.py` and mount into the
  finance router, so the module is one surface at `/api/v1/finance`.
- `GET/POST /tax-codes`, `GET/PATCH /tax-codes/{id}` (PLAN 4.4) — list cursor-paginated; reads
  guarded by `finance.tax.read`, writes by `finance.tax.manage`. The tax endpoints live in
  `tax_router.py` and mount into the finance router (same one-surface pattern as FX).
- `POST /vendor-bills` (create draft, `finance.ap.manage`), `POST /vendor-bills/{id}/post`
  (**idempotent**, `finance.ap.manage`), `GET /vendor-bills` (paginated), `GET /vendor-bills/{id}`
  (with lines) — `finance.ap.read` (PLAN 4.5).
- `POST /vendor-payments` (create + post a payment with allocations; **idempotent**,
  `finance.ap.pay`), `POST /payment-runs` (**background job** since #26: returns
  `202 {job_id, status}` — poll `GET /api/v1/jobs/{job_id}`; **idempotent**, a replayed key
  returns the same job id; `finance.ap.pay`), `GET /vendor-payments` (paginated,
  `finance.ap.read`).
- `GET /ap-aging?as_of=&partner_id=` — the AP aging report (`finance.ap.read`). The AP endpoints
  live in `ap_router.py` and mount into the finance router (same one-surface pattern as FX/tax).
- `POST /customer-invoices` (create draft, `finance.ar.manage`), `POST /customer-invoices/{id}/post`
  (**idempotent**, `finance.ar.manage`), `GET /customer-invoices` (paginated),
  `GET /customer-invoices/{id}` (with lines) — `finance.ar.read` (PLAN 4.6).
- `POST /customer-receipts` (create + post a receipt; allocations OPTIONAL since PLAN 20.4 — the
  excess is unapplied/on-account; **idempotent**, `finance.ar.collect`),
  `POST /customer-receipts/{id}/applications` (apply an unapplied balance to open invoices;
  **idempotent**, `finance.ar.collect`), `GET /customer-receipts` (paginated, `finance.ar.read`).
- `POST /dunning-runs` (advance dunning levels on overdue invoices; **idempotent**,
  `finance.ar.collect`) and `GET /ar-aging?as_of=&partner_id=` (`finance.ar.read`). The AR endpoints
  live in `ar_router.py` and mount into the finance router (same one-surface pattern as FX/tax/AP).

Writes commit through `run_in_uow` (D-011), so audit rows ride the same transaction and the
event semantics will be identical to seed/CLI once finance publishes events.

### Conditional requests on reference lists (PERFORMANCE §3 / D-035, closes #28)

The **slow-changing reference** list endpoints support `ETag` / `If-None-Match` so a client (and the
SPA's TanStack Query cache) can revalidate cheaply: a matching `If-None-Match` returns **304 Not
Modified** with no body, skipping the page query entirely (the 304 path runs the auth load + one
ETag aggregate = 2 statements vs the 200 path's 3). The endpoints that carry an ETag:

- `GET /accounts`, `GET /account-groups`
- `GET /currencies`, `GET /tax-codes`
- `GET /fiscal-years`, `GET /fiscal-periods`
- `GET /posting-defaults`

Transactional/fast-changing lists deliberately carry **no** ETag: `journal-entries`, `vendor-bills`,
`customer-invoices`, `customer-receipts`, `vendor-payments`, `exchange-rates` (rate history),
`bank-statements`, `depreciation-runs`, `fx-revaluation-runs`, and `jobs`.

**Validator semantics** (core/conditional.py, D-035). The ETag is a **collection-level WEAK**
validator computed from ONE cheap aggregate — `SELECT COUNT(id), MAX(updated_at)` over the tenant's
rows — formatted `W/"<count>-<max_updated_micros>-<tenant8>-<request_fingerprint>"`. Any insert
moves the count; any update moves `MAX(updated_at)` (TimestampMixin's `onupdate`); a delete moves
the count — so the validator flips on any change to the collection. Because it is collection-level,
**any** change to the collection invalidates **every** page's cached validator (acceptable for small
reference sets). The aggregate is automatically **tenant-scoped** by the D-007 listener, and the
`tenant8` component makes a cross-tenant 304 impossible even in theory. The `request_fingerprint`
(cursor + limit + filters, reusing the pagination fingerprint) is folded in so a 304 can only ever
be served for the **identical** page request — it can never return the wrong slice.

## Accounts Payable (PLAN 4.5, D-029)

AP is keyed by an **opaque `partner_id`** — finance is the bottom dependency, so it never
FK-references a vendor master (that lives in procurement, above finance). Each AP document carries
the opaque `partner_id` plus a denormalized `partner_name`; the owning module guarantees the id.

**Bill → post → pay.** A `VendorBill` is created DRAFT (no number, no journal); the service computes
input tax per line via the shared tax engine and rolls up net/tax/gross. Posting builds the journal
entry (document_type `AP_INVOICE`): **Dr** each expense/asset line (net) + **Dr** input tax (to the
tax code's receivable account) + **Cr** the AP control account for the gross, with the opaque
`partner_id` stamped on the AP line. The bill then claims its gapless system number (`BILL-…`), links
bill→journal (docflow `posts`), sets `open_amount = gross` and status POSTED, and publishes
`VendorBillPosted`. FX translation at posting is the journal engine's standard machinery (D-019).

**The 3-way-match-triggered bill (PLAN 6.4, D-042).** When procurement posts an invoice match it
PUBLISHES `InvoiceMatched`; `finance/handlers.create_bill_for_match` subscribes and builds + posts a
vendor bill whose line accounts are the **GR/IR clearing** account (the received-goods portion at PO
cost) and the **purchase-price-variance** account (any in-tolerance invoice-vs-PO price difference),
crediting the **AP control** posting default — i.e. **Dr GR/IR + Dr/Cr PPV / Cr AP** (+ input tax).
Because GR/IR is debited at *exactly* the PO cost the goods receipt credited it at receipt, the GR/IR
clearing account nets to zero once a PO is fully received and billed — the procure-to-pay loop closes
(the price difference lands in PPV). The bill is built through the SAME `create_vendor_bill` +
`post_vendor_bill` service, so every AP/journal invariant fires; the handler runs in the match's
transaction (a closed invoice period rolls the whole match post back). New posting defaults:
`purchase_price_variance`, `ap_control`.

**Open-item clearing.** A `VendorPayment` is created and posted in one step. It validates the cleared
bills are open, same partner, same currency, none over-allocated; posts a journal entry
(document_type `PAYMENT`): **Dr** AP control (Σ allocated) + **Cr** bank (the cash amount), reduces
each bill's `open_amount` (status → PARTIALLY_PAID/PAID), writes `VendorPaymentAllocation` rows,
links payment→bills (docflow `pays`), claims its number (`PAY-…`), and publishes
`VendorPaymentPosted`. `open_amount` is the only stored balance — aging projects over it.

**Realized FX at payment (D-019).** When the bill currency ≠ functional, the AP control was credited
at the bill's posting rate (R1) but the bank pays at the payment-date rate (R2). The functional
difference per cleared bill — `functional-at-bill-rate − functional-at-payment-rate` over the cleared
transaction amount — is the realized gain/loss, posted to the `fx_realized_gain`/`fx_realized_loss`
posting-default account **inside the same payment entry** so it balances in functional. The entry's
functional amounts are set explicitly and posted with the journal engine's `skip_translation` (it
would otherwise re-rate the whole entry at one rate); the realized-FX line is denominated in the
functional currency. When the payment currency *is* the functional currency, R1 = R2 and there is no
FX line.

**Payment run.** `POST /payment-runs` selects POSTED/PARTIALLY_PAID bills with `open_amount > 0` due
on or before the given date (optionally one partner), groups them by `(partner, currency)`, and pays
each group's due bills in full — one payment per group. Since #26 the run executes as a background
job (PERFORMANCE §3): the endpoint returns `202 {job_id}` and the created payment ids/numbers arrive
in the job's `result` via `GET /api/v1/jobs/{job_id}`.

**Aging.** `GET /ap-aging` is a pure projection over open bills: each bill's `open_amount` lands in
the bucket for `as_of − due_date` days (current / 1-30 / 31-60 / 61-90 / over-90), per partner and
rolled up. An earlier `as_of` shifts balances toward the lower buckets.

## Accounts Receivable (PLAN 4.6, D-029)

AR is the AP mirror with the **sign flipped** — same opaque-`partner_id` keying (the customer master
lives in sales, above finance, so finance never FK-references it; D-029) — plus **dunning**. Each AR
document carries the opaque `partner_id` + a denormalized `partner_name`.

**Invoice → post → receipt.** A `CustomerInvoice` is created DRAFT (no number, no journal); the
service computes output tax per line via the shared tax engine and rolls up net/tax/gross. Posting
builds the journal entry (document_type `AR_INVOICE`): **Dr** the AR control account for the gross
(with the opaque `partner_id` stamped on the AR line) + **Cr** each revenue line (net) + **Cr** output
tax (to the tax code's payable account). The invoice then claims its gapless system number (`INV-…`),
links invoice→journal (docflow `posts`), sets `open_amount = gross` and status POSTED, and publishes
`CustomerInvoicePosted`. FX translation at posting is the journal engine's standard machinery (D-019).

**Open-item clearing.** A `CustomerReceipt` is created and posted in one step. It validates the
cleared invoices are open, same partner, same currency, none over-allocated; posts a journal entry
(document_type `PAYMENT`): **Cr** AR control (Σ allocated) + **Dr** bank (the cash received), reduces
each invoice's `open_amount` (status → PARTIALLY_PAID/PAID), writes `CustomerReceiptAllocation` rows,
links receipt→invoices (docflow `receipts`), claims its number (`RCT-…`), and publishes
`CustomerReceiptPosted`. `open_amount` is the only stored balance — aging projects over it.

**Realized FX at receipt (D-019).** When the invoice currency ≠ functional, the AR control was
debited at the invoice's posting rate (R1) but the bank receives at the receipt-date rate (R2). The
functional difference per cleared invoice — `functional-at-receipt-rate − functional-at-invoice-rate`
over the cleared transaction amount — is the realized gain/loss, posted to the
`fx_realized_gain`/`fx_realized_loss` posting-default account **inside the same receipt entry** so it
balances in functional. The entry's functional amounts are set explicitly and posted with the journal
engine's `skip_translation`; the realized-FX line is denominated in the functional currency. The
realized-FX math is shared with AP in `service/clearing_fx.py` (AP debits the control to clear, AR
credits it — `control_is_debit` flips the sign; the gain/loss direction inverts accordingly). When
the receipt currency *is* the functional currency, R1 = R2 and there is no FX line.

**Unapplied (on-account) receipts — deposits (PLAN 20.4, D-084).** `allocations` is optional and
`amount` need only be **>=** their sum. The excess is the receipt's `unapplied_amount`, credited to
the `customer_advances` posting-default account (a LIABILITY — money taken before an invoice exists
is owed back, not earned) on a line carrying `partner_type` + `partner_id`, so the pooled control
reconciles per customer. A receipt with NO allocations is a pure advance deposit. `amount` *below*
the allocation sum is still refused (`finance.receipt_allocation_sum_mismatch`) — that is #73 with
the sign flipped. A tenant that never mapped `customer_advances` gets
`finance.posting_default_unmapped` (422) the first time it takes on-account money; the
allocation-for-allocation path is unchanged, including its statement budget.

`POST /customer-receipts/{id}/applications` (idempotent, `finance.ar.collect`) spends that balance:
it validates the target invoices exactly as a direct allocation does (open, same partner, same
currency, not over the open amount), refuses more than `unapplied_amount`
(`finance.receipt_apply_exceeds_unapplied`), and posts ONE reclass entry through the same
`clearing_fx` builder — **Dr** advance control + **Cr** AR control (at each invoice's frozen rate) +
the realized-FX line for the difference. The receipt keeps pointing at the entry that received the
cash (a posted entry is immutable, D-017); the reclass is reachable through the doc flow, and the
application publishes `CustomerReceiptPosted` the way a direct receipt does, so an invoice never
flips to PAID silently. `queries.customer_unapplied_balance(...)` reads a partner's on-account money
— deliberately a separate number from `customer_open_balance`, since a deposit is a liability, not a
negative receivable.

The advance leg's functional amount is **read back off the posted credit line and telescoped**, not
recomputed as `amount x rate`: the liability was credited once as one quantized figure, so
re-deriving each application's debit would quantize N times against that one rounding and a deposit
applied in PARTS (check-in, then settlement) would never fully clear — EUR 100 at 1.20 applied
33.33 / 33.33 / 33.34 debits 120.01 against a credit of 120.00, silently, because the realized-FX
line absorbs the difference. The balance itself is drawn down under a `with_for_update` row lock
(PG row lock, SQLite no-op — D-020/D-036) so two concurrent applications cannot both spend it, over
a portable `CHECK (unapplied_amount >= 0)` floor.

**Dunning.** `POST /dunning-runs` advances reminder levels. For each OPEN overdue invoice it computes
the level its days-overdue earns from `DUNNING_THRESHOLDS` (level 1 at 7 days past due, 2 at 30, 3 at
60); if that exceeds the invoice's current `dunning_level`, it raises the invoice to it and stamps
`last_dunned_date = as_of`, recording a notice (partner, invoice, new level — a collections proposal
list). It posts **no journal** — dunning is state only. It is idempotent-ish per day: re-running the
same `as_of` advances nothing already at its earned level, so a second same-day run returns an empty
list; a not-yet-overdue invoice stays at level 0.

**Aging.** `GET /ar-aging` is a pure projection over open invoices: each invoice's `open_amount`
lands in the bucket for `as_of − due_date` days (current / 1-30 / 31-60 / 61-90 / over-90), per
partner and rolled up — identical to AP aging on the receivable side.

## Controlling — cost/profit centres + allocations (PLAN 4.7, D-021)

**CO is a projection of the universal journal — there is no separate CO ledger.** This is the
load-bearing principle (D-021): every cost-centre report is a `SUM` over `fin_journal_lines` grouped
by their `cost_center_id` dimension, exactly as P&L/balance-sheet are projections grouped by account.
Controlling therefore adds only *master data* (the dimensions) and *one more kind of journal entry*
(an allocation), never stored totals.

**Cost / profit centres are journal-line dimensions.** A `CostCenter` (`fin_cost_centers`) and a
`ProfitCenter` (`fin_profit_centers`) are tenant-scoped master data with a self-referential
`parent_id` hierarchy the service keeps **acyclic** (the same walk-the-parent-chain cycle guard the
account-group tree uses) and a unique `(tenant, code)`. A cost centre may carry a
`default_profit_center_id`. Their ids are what a journal line stores in `cost_center_id` /
`profit_center_id`.

**Journal dimension integrity is enforced at the SERVICE layer (D-022).** `fin_journal_lines` is
trigger-bearing, so per D-022 it must **not** gain FKs — the dimension columns stay opaque `sa.Uuid`.
The integrity the absent FK would give is provided by `service/journal.create_draft_entry`, which now
validates that every line's `cost_center_id` / `profit_center_id` exists for the tenant (via
`queries.cost_center_exists` / `profit_center_exists`) and raises `finance.journal_cost_center_not_found`
/ `finance.journal_profit_center_not_found` (422) otherwise. A valid dimension posts and the line
carries it, so the projection sees it.

**Allocation rules.** An `AllocationRule` (`fin_allocation_rules`) names a **source** cost centre
whose net period cost is redistributed, a `basis`, and N `AllocationRuleTarget` rows (each a target
cost centre + a `weight`). `basis` is `PERCENT` (weights must sum to **100**, validated) or
`FIXED_WEIGHT` (any positive weights, distributed **proportionally**). The source can never be a
target, and a target appears at most once.

**Running an allocation** (`POST /allocation-runs`, `run_allocation(rule, period, run_date)`):

1. Compute the source cost centre's **net functional balance** for the period via
   `queries.cost_center_balance` (Σ posted functional debit − credit on lines carrying the source
   `cost_center_id` in the period). That is the amount to allocate.
2. Distribute it across the targets by their weights with `core.money.allocate` (largest-remainder),
   so the parts sum **EXACTLY** to the source amount — e.g. 1000 split three ways gives
   333.34 / 333.33 / 333.33 with no lost cent.
3. Post **ONE balanced journal entry** on a single dedicated `cost_allocation` posting-default
   account: one line **crediting** the source cost centre (moving the cost out) and N lines
   **debiting** each target cost centre, every line tagged with its `cost_center_id`. The account
   nets to zero; cost moves between cost centres purely via the line dimension, so cost-centre reports
   (journal projections) reflect the reallocation. (A net-credit source flips the sides.)
4. Claim the gapless `ALLOC-…` number, link run→journal in docflow (`posts`), track the run in
   `fin_allocation_runs`, and publish `AllocationPosted`.

The run is **idempotent** (a second run for the same `(rule, period)` returns the existing run) and
**reversible** (its journal entry reverses like any other; a re-run after correction relies on that).
A zero source balance is a clear 422 (`finance.allocation_zero_balance`) — nothing to allocate.

## Financial statements — every report is a projection of ONE aggregate (PLAN 4.8, D-021)

**This is the payoff of the universal journal.** Every statement Atlas produces — trial balance,
P&L, balance sheet, cash flow, cost-centre report, margin-by-product — is a **projection of one
base aggregate over `fin_journal_lines`**. There are **no stored totals, no balance tables, no
materialized views** (CLAUDE.md rule 1, D-021). Because every statement reads the **same** query
with the **same** predicate, each is provably consistent with the trial balance by construction —
FI/CO reconciliation is eliminated, not reconciled.

**The single base aggregate** (`service/statements/base._account_balances`):

```python
select(JournalLine.account_id,
       func.sum(functional_debit_amount - functional_credit_amount))
.where(tenant_id == ..., is_posted == True, posting_date <= date_to [, >= date_from])
.group_by(account_id)
```

It returns `{account_id: signed_balance}`, debit-positive (ASSET/EXPENSE positive, the credit-side
types negative). **No header join** is needed — the line denormalizes `tenant_id`/`posting_date`/
`is_posted` during the two-flush posting protocol (D-017). `MoneyType` type propagation keeps the
`SUM` exact on both engines (D-015). Every statement below builds on exactly this.

- **Trial balance** (`as_of`): the signed balance split per account onto its natural debit/credit
  side. Asserts the universal-journal **debit == credit** identity into `is_balanced` + the totals —
  every posted entry balances (the DB balance trigger), so the whole ledger does.
- **P&L** (`date_from..date_to`): REVENUE and EXPENSE accounts over the range, laid out under the
  `account_group` hierarchy with a subtotal per group. **Net income = revenue − expense**,
  hand-checkable and equal to the figure the balance sheet folds into retained earnings.
- **Balance sheet** (`as_of`): ASSET/LIABILITY/EQUITY cumulative to date, grouped by `account_group`.
  **Retained earnings is computed on the fly** — net income over *all* history to `as_of`
  (`net_income_signed`), presented as a synthetic **"Current & accumulated earnings"** equity line.
  This is exact by construction (every balanced posting moved equal debits and credits), so
  **Assets == Liabilities + Equity** holds identically — asserted into `is_balanced` + the totals.
  v1 needs **no year-end carryforward**: deriving retained earnings from genesis makes that sound
  rather than a hole.
- **Cash flow, indirect** (`date_from..date_to`): starts from net income for the period, then adds
  the signed deltas of every **non-cash** balance-sheet account between `date_from − 1` and `date_to`,
  bucketed by `cash_flow_category` (OPERATING/INVESTING/FINANCING). The **built-in self-check**: the
  net change those movements imply MUST equal the actual movement in `is_cash_equivalent` accounts
  over the period — double-entry forces them equal. `is_reconciled` exposes that identity, and
  `net_change_from_activities` / `cash_account_movement` expose the cash delta **both ways** so any
  discrepancy is visible, not hidden.
- **Cost-centre report** (`date_from..date_to`, optional `cost_center_id`): the same aggregate
  grouped by the line's `cost_center_id` dimension and account — CO without a separate ledger.
- **Margin by product** (`date_from..date_to`): revenue − COGS grouped by the line's `item_id`
  dimension, per item with revenue / cogs / margin / margin %. Sparse until inventory posts COGS with
  `item_id` (PLAN 5), but structurally correct now and tested with item-tagged journal lines.

**No stored totals, ever.** Post another entry and the trial balance, P&L and balance sheet reflect
it on the very next read — there is nothing to refresh. `queries.account_balances` / `queries.net_income`
expose the same aggregate to the reporting module (PLAN 13) so its views are projections of the
*same* query, never a copy.

**Performance** (D-021): the partial covering index `ix_fin_journal_lines_proj` ON
`(tenant_id, account_id, posting_date) WHERE is_posted` — declared with **both** dialect predicates
(`postgresql_where` AND `sqlite_where`) — plus `INCLUDE (functional_debit_amount,
functional_credit_amount)` on Postgres for index-only scans (ignored on SQLite). Migration **0015**
brings the index up to this covering shape (0009 created the bare partial form). The migration uses
plain `CREATE/DROP INDEX`, **not** `batch_alter_table`, so SQLite does not copy-rebuild the
trigger-bearing `fin_journal_lines` table — the line-immutability trigger **survives the migration**
(a pg-marked guard test proves it still fires afterwards).

**API** (`/api/v1/finance/statements/*`, all `GET`, all guarded by `finance.statements.read`):
`trial-balance?as_of=`, `profit-loss?date_from=&date_to=`, `balance-sheet?as_of=`,
`cash-flow?date_from=&date_to=`, `cost-center-report?date_from=&date_to=&cost_center_id=`,
`margin-by-product?date_from=&date_to=`. Every response carries its self-check flag (`is_balanced` /
`is_reconciled`) so the guarantee is visible on the wire.

## Bank reconciliation (PLAN 4.9)

Match what the BANK says happened (`fin_bank_statements` + `fin_bank_statement_lines`) against
what the JOURNAL says happened — without ever mutating the journal. A statement is an EXTERNAL
document: it registers in `core_documents` (DocumentMixin) with `doc_number` NULL (D-012
numbering covers documents Atlas issues; a statement is identified by bank account + date +
`source_filename`).

**CSV import contract** (`service/bank_csv.py` — the only v1 format; MT940/CAMT.053 parsers are
a parity-doc later that will feed this same pipeline):

```
value_date,amount,description,counterparty_ref
2026-03-02,100.00,Customer payment ACME,INV-1
2026-03-05,-12.50,Bank fee,
```

- Header must match exactly; ISO-8601 dates; decimal-point amounts SIGNED from the bank
  account's perspective (positive = money in, negative = money out); description required;
  `counterparty_ref` optional. Amounts quantize HALF_UP to the statement currency (D-015).
- Malformed rows are collected into a per-row error report (`details.row_errors`, 1-based data-
  row numbers, capped at 50) and the WHOLE file is rejected `422 finance.statement_csv_invalid`
  — no partial statements.
- The statement must be internally consistent: `closing_balance == opening_balance + Σ(line
  amounts)` or `422 finance.statement_unbalanced`.
- The target account must exist AND be `is_cash_equivalent`
  (`422 finance.bank_account_not_cash_equivalent`).

**Import size threshold** (PERFORMANCE §3): `POST /bank-statements` counts the CSV's data rows —
up to **1000** (`BANK_IMPORT_SYNC_MAX_LINES`) the import runs inline and returns `201` with the
statement; above that it submits a `finance.bank_statement_import` job and returns
`202 {job_id}` for `/api/v1/jobs/{id}` polling (the handler calls the SAME `import_statement`;
the statement records its `import_job_id`). Either way the lines are written with ONE
ORM-enabled executemany insert (PERFORMANCE §2) — a 1200-line import executes ~6 SQL statements
total, asserted by a query-counter test. The endpoint is IDEMPOTENT (D-013): a replayed key
returns the same statement (or the SAME job id).

**Match rules** (`suggest-matches`, priority order, set-based passes over candidate maps built
from two queries — no per-line N+1):

1. exact signed amount + same date (`value_date == posting_date`);
2. exact signed amount within ±3 days (nearest date wins; ties take the earlier posting).

Candidates are POSTED journal lines on the statement's bank account in the statement currency;
the comparison key is `transaction_debit_amount − transaction_credit_amount` (a debit to the
bank account is money in). A journal line is consumed by at most ONE statement line tenant-wide
(rejecting a suggestion releases it). **v1 boundary** (documented cut): no document-number-in-
description heuristic (rule 3), no partial/many-to-one matching, no configurable tolerance, no
auto-clearing rules engine — rules 1+2 cover the dominant exact-amount case.

**Statuses.** Line: `UNMATCHED -> SUGGESTED -> MATCHED` (confirm) or back to `UNMATCHED`
(reject); `UNMATCHED -> CLEARED` (clearing posting). A line is RESOLVED when MATCHED or
CLEARED. Statement (derived, recomputed on every transition): `IMPORTED` (nothing resolved) ->
`PARTIALLY_RECONCILED` (some) -> `RECONCILED` (all).

**Clearing** (`/bank-statement-lines/{id}/clear`, IDEMPOTENT): for a bank-only line with no
system-side counterpart (fees, interest) it posts a REAL journal entry through the unchanged
D-017 protocol — money in = Dr bank / Cr contra, money out = Dr contra / Cr bank — where the
contra defaults to the `bank_unmatched_clearing` posting default (D-019 purpose wiring) unless
an explicit `contra_account_id` is given. The entry is `JOURNAL`-typed, gapless-numbered, and
docflow-linked statement → `posts` → entry (D-012).

**API** (`/api/v1/finance`, PERFORMANCE §6: paginated, indexed, ≤3-query lists):
`POST /bank-statements` (`finance.bank.import`, Idempotency-Key required, 201/202 split),
`GET /bank-statements` + `/{id}` (with progress counts) + `/{id}/lines?status=`
(`finance.bank.read`), `POST /bank-statements/{id}/suggest-matches` (rerun-safe),
`POST /bank-statement-lines/{id}/confirm-match` | `/reject-suggestion` | `/clear`
(`finance.bank.reconcile`; clear requires an Idempotency-Key). Statement lists sort by
`(statement_date DESC, id)` — deliberately no created_at seek key on SQLite (see the tracked
core-pagination datetime issue).

## Asset accounting lite (PLAN 4.10)

The parity-doc scope is deliberately "lite": a register plus straight-line and
declining-balance depreciation runs posting journals. **No** transfers, retirements with
gain/loss, revaluation, parallel depreciation areas or assets under construction — those are
the recorded "later" path (extend the register with lifecycle events reusing this run poster).

**Lifecycle.** `fin_assets` rows are created DRAFT (registered in `core_documents` with
`doc_number` NULL) and freely editable; **activation** claims the gapless `AST-YYYY-NNNNN`
number (the D-012 claim-at-permanence moment) and flips ACTIVE. `activate` takes
`capitalize`: `true` ALSO posts the acquisition journal — Dr the asset's balance-sheet
account / Cr the `asset_acquisition_clearing` posting default (D-019 purpose wiring), dated
`acquisition_date` (must fall in an OPEN period), docflow-linked asset → `posts` → entry;
`false` just activates, for assets entered with opening balances already on the books. Once
every cent of `cost − salvage` is depreciated the asset flips FULLY_DEPRECIATED and drops out
of future runs. Validation at create/update: the asset + accumulated-depreciation accounts
must be postable ASSET accounts, the expense account a postable EXPENSE account, salvage <
cost, the declining rate required (0 < rate ≤ 100) exactly when the method is
DECLINING_BALANCE, and the optional `cost_center_id` dimension must exist (D-022
service-level integrity).

**The two methods + exactness guarantees** (`compute_depreciation(asset, period_index,
prior_accumulated)`; `period_index` is the asset's 1-based position in its own schedule =
prior entry count + 1):

- **STRAIGHT_LINE** — drift-free cumulative formulation:
  `amount(n) = quantize((cost − salvage) × n / life, HALF_UP) − prior_accumulated`, and the
  final period (`n ≥ life`) takes exactly `(cost − salvage) − prior_accumulated`. Because each
  period is cumulative-to-date minus what was already taken (largest-remainder-style), the
  per-period amounts can never drift and the schedule sums to `cost − salvage` EXACTLY —
  10000/12 months yields 833.33/833.34 alternating and totals 10000.00 to the cent.
- **DECLINING_BALANCE** — `amount(n) = quantize(NBV_start × annual_rate% / 12, HALF_UP)`,
  floored at salvage: when the naive charge would cross the floor the period takes
  `NBV_start − salvage` and NBV lands EXACTLY on salvage; when the schedule exhausts
  (`n ≥ life`) the final period likewise takes the remainder to salvage.

**Run mechanics** (`run_depreciation`, set-based per PERFORMANCE §2 — the SQL statement count
is CONSTANT in the asset count): select eligible ACTIVE assets via a NOT EXISTS anti-join on
`fin_depreciation_entries` for the target period; read every asset's prior schedule position +
accumulated total in ONE grouped aggregate (no N+1); compute per-asset amounts (zero amounts
skipped); bulk-insert the entries with ONE executemany (each freezing `accumulated_after` /
`nbv_after` as the per-entry audit trail); and post **ONE** journal entry (document_type
DEPRECIATION) with lines GROUPED per (expense account, cost centre) on the debit side and per
accumulated-depreciation account on the credit side — never per-asset lines. The run claims
the gapless `DEP-YYYY-NNNNN` number and is docflow-linked run → `posts` → entry.
**Idempotency is by construction**: `UNIQUE(tenant, asset_id, fiscal_period_id)` means an
asset depreciates once per period ever (overlapping runs collide at the DB); a re-run for a
finished period finds nothing eligible and returns the existing POSTED run unchanged; and the
endpoint requires an Idempotency-Key (D-013). Closed periods are rejected at the service
(`422 finance.period_closed`) with the journal's period trigger as the bypass-proof backstop;
`run_date` must fall inside the target period (the trigger re-derives the period from the
posting date, so a mismatch would post elsewhere).

**Run size threshold** (PERFORMANCE §3): `POST /depreciation-runs` counts the period's
eligible assets — up to **100** (`DEPRECIATION_RUN_SYNC_MAX_ASSETS`) the run executes inline
(201 with the run); above that it submits a `finance.depreciation_run` job and returns
`202 {job_id}` for `/api/v1/jobs/{id}` polling (the handler calls the SAME
`run_depreciation`; a replayed key returns the same run or the SAME job id).

**Register as projection** (`GET /asset-register?as_of=`): per activated asset acquired by
`as_of` — cost, accumulated depreciation to date, NBV — RECOMPUTED in one statement as
`SUM(fin_depreciation_entries.amount)` over the fiscal periods ending on or before `as_of`.
No NBV or accumulated total is stored on the asset row; the entries' `*_after` columns are
per-entry audit trail only (the D-021 no-stored-totals discipline applied to the sub-ledger).

**API** (`/api/v1/finance`, PERFORMANCE §6: paginated, indexed, ≤3-query lists):
`POST /assets` + `PATCH /assets/{id}` (DRAFT only) + `POST /assets/{id}/activate`
(Idempotency-Key required) (`finance.asset.manage`), `GET /assets?status=` + `/{id}`
(`finance.asset.read`), `POST /depreciation-runs` (`finance.depreciation.run`,
Idempotency-Key required, 201/202 split), `GET /depreciation-runs?fiscal_period_id=` + `/{id}`
+ `/{id}/entries`, `GET /asset-register?as_of=` (`finance.asset.read`). Asset lists sort by
`(acquisition_date DESC, id)`, runs by `(run_date DESC, id)`.
