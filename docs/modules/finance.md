# Finance (`backend/app/modules/finance/`)

Finance is the first business module and the **bottom of the dependency order** (STRUCTURE §5):
every other module may read `finance/queries.py`, and finance imports no other module. The
full normative design lives in [docs/architecture.md](../architecture.md) (D-017…D-022); this
guide is the operator/contributor map, and it grows with each finance task (PLAN 4.1…4.10).

## Status

PLAN 4.1 (this task) lays the **schema foundation**: the chart of accounts and fiscal
years/periods with the open/close lifecycle. The universal journal (D-017), the DB-level
period-posting trigger (D-018), AP/AR, payments and FX land in PLAN 4.2…4.10.

| File | Concern | Key decision |
|---|---|---|
| `constants.py` | `AccountType`, `NormalBalance`, `CashFlowCategory`, `PeriodStatus` enums; the normal-balance mapping; permission keys | D-021, D-018, D-009 |
| `models.py` | `Account`, `AccountGroup`, `FiscalYear`, `FiscalPeriod` | D-021, D-018 |
| `schemas.py` | Create/Update/Read/Filter request/response schemas | — |
| `service/accounts.py` | chart-of-accounts business logic | D-021 |
| `service/periods.py` | fiscal years/periods + open/close lifecycle | D-018 |
| `queries.py` | the cross-module read interface finance **exposes** | STRUCTURE §5 |
| `router.py` | thin HTTP layer at `/api/v1/finance` | — |

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

### The journal-posting seam (deferred to 4.2)

D-018 mandates period-close enforcement at **both** the service and DB level. This task builds the
period state and the service-level lifecycle now and leaves a **clearly-marked, real** extension
point — it is not a stub:

- **`service/periods.assert_period_closable(...)`** is the seam. Today it rejects closing an
  already-closed period (the only invariant a close can violate before the journal exists). When
  the journal lands, **4.2 extends this same function in place** to also refuse closing a period
  that still has `DRAFT` journal entries dated within it (the service-level half of D-018).
- The **DB-level posting-rejection trigger** fires on `fin_journal_entries`, which does not exist
  until 4.2 — so migration `0008` ships **no triggers**, and the trigger lands with the journal
  table in the next revision. `core/exceptions.py` already pre-registers the
  `ATLAS_PERIOD_CLOSED` → `finance.period_closed` token so the backstop surfaces through the
  standard error envelope the moment the trigger exists.

## The `queries.py` contract (what other modules read)

Finance exposes exactly three stable read functions (STRUCTURE §5 — everyone may import these):

- `find_period_for_date(session, tenant_id, on_date) -> FiscalPeriod | None`
- `get_period_status(session, tenant_id, on_date) -> PeriodStatus | None`
- `account_exists(session, tenant_id, code) -> bool`

Inventory and sales call `get_period_status` to refuse stock/sales documents dated into a closed
period before they reach the GL; the journal calls `find_period_for_date` to resolve an entry's
period from its posting date.

## Permissions (D-009)

| Key | Guards |
|---|---|
| `finance.account.read` | read accounts and account groups |
| `finance.account.manage` | create/edit accounts and account groups |
| `finance.period.read` | read fiscal years and periods |
| `finance.period.manage` | create fiscal years, open/close periods |

Journal, AP, AR and payment keys are registered by their own tasks (4.2+).

## API (`/api/v1/finance`)

- `GET/POST /accounts`, `GET/PATCH /accounts/{id}` — list uses cursor pagination + the `Page`
  envelope; filters (`account_type`, `is_postable`, `is_active`, `account_group_id`) fold into
  the cursor fingerprint.
- `GET/POST /account-groups`
- `GET/POST /fiscal-years` (POST generates the periods), `GET /fiscal-periods`
- `POST /fiscal-periods/{id}/close` and `/open` — action sub-resources (STRUCTURE §7), guarded by
  `finance.period.manage`.

Writes commit through `run_in_uow` (D-011), so audit rows ride the same transaction and the
event semantics will be identical to seed/CLI once finance publishes events.
