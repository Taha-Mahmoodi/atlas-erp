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
