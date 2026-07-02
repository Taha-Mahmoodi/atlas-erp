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

**Latest release: `v0.3.0` — all backend modules complete.** Every line-of-business module is built on the v0.1.0 core platform and tested on both SQLite and PostgreSQL. The REST API surface is complete; the web frontend is next (Phase 15).

- **Finance & Controlling** ([guide](docs/modules/finance.md)) — universal journal (double-entry enforced in code *and* DB triggers, immutable posted entries), fiscal periods with closed-period DB guards, multi-currency with realized + auto-reversing unrealized FX, line-level tax, AP/AR with background payment runs, aging and dunning, cost/profit centers and allocations, bank reconciliation, asset accounting with depreciation runs, and all financial statements as pure journal projections
- **Inventory & Warehouse** ([guide](docs/modules/inventory.md)) — items, categories, UoM conversions, lot/serial; warehouses, bins, and stock moves as the on-hand single source of truth; moving-average *and* FIFO costing with same-transaction COGS; physical and cycle counts with variance posting
- **Procurement** ([guide](docs/modules/procurement.md)) — vendor master, requisition → RFQ → PO with data-driven approval thresholds, goods receipt with GR/IR clearing, 3-way match → AP bill, reorder-point requisitions
- **Sales & Distribution** ([guide](docs/modules/sales.md)) — customer master with pricing, quote → order with ATP and credit-limit checks, delivery with partial shipments (stock issue + COGS), billing → revenue, and RMA returns with credit notes
- **Manufacturing** ([guide](docs/modules/manufacturing.md)) — BOMs, work centers, routings; production orders with WIP journals; MRP run with a rough capacity check
- **Quality & Maintenance** ([quality](docs/modules/quality.md) · [maintenance](docs/modules/maintenance.md)) — goods-receipt inspection lots with disposition; equipment register with corrective and preventive orders
- **HR & Payroll** ([guide](docs/modules/hr.md)) — employees with masked compensation and org chart, leave accruals with approval, time tracking allocated to projects/cost centers, and a gross→net payroll run posting a balanced journal
- **Projects** ([guide](docs/modules/projects.md)) — projects and WBS costing objects with a cost report
- **CRM** ([guide](docs/modules/crm.md)) — leads → opportunities kanban, activities, and conversion
- **Reporting** ([guide](docs/modules/reporting.md)) — role-based dashboard KPIs and a generic whitelist-driven, tenant-scoped report builder
- **Industry templates & onboarding** ([guide](docs/modules/industry.md)) — five industry templates (manufacturing, retail, professional-services, healthcare, construction) applied idempotently, and a one-call tenant onboarding wizard that provisions a tenant + admin + the full template configuration in a single transaction
- **Admin** ([guide](docs/modules/admin.md)) — user/role management, permission catalog, audit-log viewer, and per-tenant number-sequence viewer

Built on the v0.1.0 core ([core module guide](docs/modules/core.md)): non-bypassable row-level multi-tenancy, JWT auth (argon2id, rotating refresh sessions), RBAC as data with field masking, in-transaction append-only audit, an in-process domain-event bus, document-flow chains, gapless numbering, idempotency keys, keyset pagination, an in-process background-job runner, gzip + conditional (ETag) reference reads, and a wall-clock performance budget suite.

Cross-module effects flow through the event bus (e.g. delivery → stock issue → COGS posting), never direct imports. Several correctness issues found during the build are tracked as open issues and listed in each release's notes; see the [v0.3.0 release notes](https://github.com/Taha-Mahmoodi/atlas-erp/releases) for the known-issues list before relying on a module. The web frontend and seeded `docker-compose` demo land in Phase 15–17.

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
