# Atlas ERP

[![CI](https://github.com/Taha-Mahmoodi/atlas-erp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Taha-Mahmoodi/atlas-erp/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/Taha-Mahmoodi/atlas-erp?include_prereleases)](https://github.com/Taha-Mahmoodi/atlas-erp/releases)

**Atlas is an open-source, industry-agnostic ERP platform. Its functional benchmark is SAP S/4HANA.**

Rather than inventing an ERP feature set from scratch, Atlas derives its scope from a researched parity map of S/4HANA's line-of-business modules — Finance & Controlling, Inventory & Warehousing, Procurement, Sales & Distribution, Manufacturing, Quality & Maintenance, HR, Projects — and inherits two of S/4HANA's defining design principles outright:

1. **Universal Journal** — one append-only financial line-item table is the single source of truth; every financial and controlling view (P&L, balance sheet, cost-center reports, margin analysis) is a projection of it, never a separately stored total.
2. **Document flow** — every business document records its predecessor/successor links, so the full chain (requisition → PO → goods receipt → invoice → journal) is traceable and renderable for any document.

The parity map itself lives at [docs/research/s4hana-parity.md](docs/research/s4hana-parity.md) and is kept honest: every capability is marked full / partial / out-of-scope for v1, with reasons and an upgrade path.

## Status

🚧 **Pre-alpha, under active construction.** The build journal is public: see [PLAN.md](PLAN.md) for the phased plan, [PROGRESS.md](PROGRESS.md) for the running log, and [DECISIONS.md](DECISIONS.md) for the design-decision record.

**Latest release: `v0.2.0` — Finance & Controlling.** The full FI/CO module is built on the v0.1.0 core platform and tested on both SQLite and PostgreSQL ([finance module guide](docs/modules/finance.md)):

- **Universal journal** — hierarchical chart of accounts; strict double-entry posting with debit/credit and balance enforced in code *and* DB triggers; posted entries immutable, corrected only by reversal
- **Fiscal periods** with open/closed states enforced at the service layer and by a per-dialect DB trigger (no posting into a closed period, even via raw SQL)
- **Multi-currency** — transaction + functional amounts frozen at posting; realized FX at clearing; an auto-reversing unrealized-FX revaluation run
- **Tax engine** — configurable inclusive/exclusive codes applied at line level
- **Accounts Payable / Accounts Receivable** — bills, invoices, receipts, background payment runs, aging, dunning — all posting through the journal
- **Cost & profit centers** with allocation rules and allocation runs
- **Financial statements as pure projections** of the journal — trial balance, P&L, balance sheet, indirect cash flow, cost-center and margin reports; never stored totals
- **Bank reconciliation** — CSV statement import (background job above 1k lines), set-based match suggestions, suspense clearing
- **Asset accounting lite** — register plus straight-line and declining-balance depreciation runs that post grouped journals

Built on the v0.1.0 core ([core module guide](docs/modules/core.md)): non-bypassable row-level multi-tenancy, JWT auth (argon2id, rotating refresh sessions), RBAC as data with field masking, in-transaction append-only audit, an in-process domain-event bus, document-flow chains, gapless numbering, idempotency keys, keyset pagination, an in-process background-job runner, gzip + conditional (ETag) reference reads, and a wall-clock performance budget suite.

Inventory & Warehouse is next on the plan.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL (SQLite-compatible demo) · Alembic · Pydantic v2 |
| Frontend | React 18 · TypeScript · Vite · TanStack Query + Router · Tailwind · in-house component library |
| Platform | Multi-tenant (row-level isolation) · JWT + RBAC-as-data · append-only audit · in-process domain-event bus · REST `/api/v1` |

## Quickstart

A `docker-compose up` quickstart (database + backend + frontend with seeded demo tenants) ships with the first runnable milestone — this section will hold the <10-step setup at that point.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch model, commit conventions, and the issue-first protocol. Security reports: [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE)
