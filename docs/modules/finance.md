# Finance (`backend/app/modules/finance/`)

Finance is the first business module and the **bottom of the dependency order** (STRUCTURE §5):
every other module may read `finance/queries.py`, and finance imports no other module. The
full normative design lives in [docs/architecture.md](../architecture.md) (D-017…D-022); this
guide is the operator/contributor map, and it grows with each finance task (PLAN 4.1…4.10).

## Status

PLAN 4.1 laid the **schema foundation**: the chart of accounts and fiscal years/periods.
PLAN 4.2 added the **universal journal** (D-017) — the heart of the system — and the **four
DB-level guard triggers** (D-018/D-017). PLAN 4.3 added **multi-currency** (D-019): currencies +
rates, posting-time translation, unrealized-FX revaluation. PLAN 4.4 (this task) adds the **tax
engine**: configurable line-level tax codes + the calculation service AP/AR/Sales call. AP/AR and
payments land in PLAN 4.5…4.10.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | account/period/FX enums + normal-balance mapping; `EntryStatus`, `DocumentType`, `RateKind`, `FxRunStatus`, `TaxDirection`; permission + posting-purpose keys | D-021, D-018, D-017, D-019, D-009 |
| `models/accounts.py` | `Account` (+ `is_monetary`/`currency_code`), `AccountGroup`, `FiscalYear`, `FiscalPeriod` | D-021, D-018, D-019 |
| `models/journal.py` | `JournalEntry`, `JournalLine` (the universal journal) | D-017, D-021 |
| `models/fx.py` | `Currency`, `ExchangeRate`, `PostingDefault`, `FxRevaluationRun` | D-019 |
| `models/tax.py` | `TaxCode` (configurable line-level tax codes) | PLAN 4.4 |
| `schemas.py` | Create/Update/Read/Filter for accounts, periods, journal, **FX**, **tax** | — |
| `service/accounts.py` | chart-of-accounts business logic | D-021 |
| `service/periods.py` | fiscal years/periods + open/close lifecycle | D-018 |
| `service/journal.py` | draft creation, two-flush posting (+ FX translation), reversal | D-017, D-019 |
| `service/fx.py` | rate lookup, currency mgmt, translation | D-019 |
| `service/fx_translation.py` | posting-time line translation + largest-remainder balancing | D-019 |
| `service/fx_revaluation.py` | unrealized-FX revaluation run + auto-reversal | D-019 |
| `service/posting_defaults.py` | purpose-keyed account wiring (reused by AP/AR/COGS) | D-019 |
| `service/tax.py` | tax calculation (inclusive/exclusive, document grouping) + tax-code CRUD | PLAN 4.4 |
| `events.py` | `JournalEntryPosted`, `JournalEntryReversed` | D-011 |
| `queries.py` | the cross-module read interface finance **exposes** (+ `get_rate`, `functional_currency`, `get_tax_code`, `calculate_line_tax`) | STRUCTURE §5 |
| `router.py` / `fx_router.py` / `tax_router.py` | thin HTTP layer at `/api/v1/finance` | D-013 (idempotent post/reverse/revalue) |

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

## API (`/api/v1/finance`)

- `GET/POST /accounts`, `GET/PATCH /accounts/{id}` — list uses cursor pagination + the `Page`
  envelope; filters (`account_type`, `is_postable`, `is_active`, `account_group_id`) fold into
  the cursor fingerprint.
- `GET/POST /account-groups`
- `GET/POST /fiscal-years` (POST generates the periods), `GET /fiscal-periods`
- `POST /fiscal-periods/{id}/close` and `/open` — action sub-resources (STRUCTURE §7), guarded by
  `finance.period.manage`.
- `POST /journal-entries` (create draft), `GET /journal-entries` (paginated), `GET /{id}` (with
  lines) — `finance.journal.post` / `finance.journal.read`.
- `POST /journal-entries/{id}/post` and `/{id}/reverse` — action sub-resources, **idempotent**
  (D-013, require the `Idempotency-Key` header), guarded by `finance.journal.post` /
  `finance.journal.reverse`.
- `GET/POST /currencies`, `GET/POST /exchange-rates` (list paginated), `GET/PUT /posting-defaults`
  — guarded by `finance.fx.manage` (D-019).
- `POST /fx-revaluation-runs` (run; **idempotent**, guarded by `finance.fx.revalue`),
  `GET /fx-revaluation-runs` (D-019). The FX endpoints live in `fx_router.py` and mount into the
  finance router, so the module is one surface at `/api/v1/finance`.
- `GET/POST /tax-codes`, `GET/PATCH /tax-codes/{id}` (PLAN 4.4) — list cursor-paginated; reads
  guarded by `finance.tax.read`, writes by `finance.tax.manage`. The tax endpoints live in
  `tax_router.py` and mount into the finance router (same one-surface pattern as FX).
- `POST /vendor-bills` (create draft, `finance.ap.manage`), `POST /vendor-bills/{id}/post`
  (**idempotent**, `finance.ap.manage`), `GET /vendor-bills` (paginated), `GET /vendor-bills/{id}`
  (with lines) — `finance.ap.read` (PLAN 4.5).
- `POST /vendor-payments` (create + post a payment with allocations; **idempotent**,
  `finance.ap.pay`), `POST /payment-runs` (run a batch; **idempotent**, `finance.ap.pay`),
  `GET /vendor-payments` (paginated, `finance.ap.read`).
- `GET /ap-aging?as_of=&partner_id=` — the AP aging report (`finance.ap.read`). The AP endpoints
  live in `ap_router.py` and mount into the finance router (same one-surface pattern as FX/tax).
- `POST /customer-invoices` (create draft, `finance.ar.manage`), `POST /customer-invoices/{id}/post`
  (**idempotent**, `finance.ar.manage`), `GET /customer-invoices` (paginated),
  `GET /customer-invoices/{id}` (with lines) — `finance.ar.read` (PLAN 4.6).
- `POST /customer-receipts` (create + post a receipt with allocations; **idempotent**,
  `finance.ar.collect`), `GET /customer-receipts` (paginated, `finance.ar.read`).
- `POST /dunning-runs` (advance dunning levels on overdue invoices; **idempotent**,
  `finance.ar.collect`) and `GET /ar-aging?as_of=&partner_id=` (`finance.ar.read`). The AR endpoints
  live in `ar_router.py` and mount into the finance router (same one-surface pattern as FX/tax/AP).

Writes commit through `run_in_uow` (D-011), so audit rows ride the same transaction and the
event semantics will be identical to seed/CLI once finance publishes events.

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
each group's due bills in full — one payment per group.

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
