"""Hospitality module (PLAN 19) — the FOURTEENTH business module: restaurant ordering.

Phase 19 is the restaurant half of the hospitality vertical scoped in
``docs/research/hospitality-industry-plan.md``: a menu, order tickets, ingredient depletion, and the
property's own website reading the menu and posting orders over the Phase 18 machine credential
(D-069). The hotel half (rooms, folio, night audit) is Phase 20 and lives nowhere in this package
yet.

Three findings shape the design; they are why the obvious implementation is wrong, and each is
measured in the spec rather than asserted:

- **Availability is STORED, never derived (Q2).** ``atp_check`` is 3 queries per item and its
  ``on_hand - committed + on_order`` formula lets an open PO make tonight's dish read available.
  Decisively, ``collection_etag`` (``core/conditional.py``) is ``COUNT(id), MAX(updated_at)``, so
  selling the last portion moves no ``Item.updated_at`` and the website gets a 304 asserting a
  sold-out dish is available. A row of stored state the ETag aggregates over invalidates correctly
  and for free.
- **Depletion is NOT synchronous with the sale (Q4).** One ingredient ISSUE is 38 statements
  (measured, ``tests/perf/test_write_budgets.py``) and ``MAX_DISPATCHES_PER_UOW = 50`` counts
  handler invocations, so a 56-line ticket is an HTTP 500 at the guest's table. Components aggregate
  across ticket lines and issue in a background job at SEND-TO-KITCHEN, not at tender.
- **``Item.is_active`` is not availability (Q2).** It is filter-only, ``item_exists`` never reads
  it, and ``AuditMixin`` writes an audit row for a toggle a kitchen flips dozens of times a night.

Hospitality sits ABOVE inventory and manufacturing in the dependency order (STRUCTURE §5). It reads
``inventory/queries`` (item existence, on-hand) and the manufacturing BOM engine (recipes ARE BOMs —
no new item entity, no new recipe entity) DOWNWARD, and posts stock through the bus rather than by
importing inventory's service. Both are older modules that import nothing from hospitality, so the
direction is one-way and there is no cycle.
"""

# D-009 registration hook. Permission keys only reach ``rbac.catalog_keys()`` — and so only become
# grantable to a tenant — if something imports the declaring module at app-import time. Importing
# constants HERE rather than relying on a router that happens to reference a key makes the
# guarantee unconditional: ``core/bootstrap.py`` imports ``hospitality.router``, which imports this
# package first, which registers the keys. It is also the convention ``core/rbac.py`` names in its
# own catalog comment ("module __init__ files register theirs"). ``register_permissions`` is
# idempotent, so Task 6's router importing the same keys costs nothing.
#
# ``models`` is imported for the D-007 analogue of the same guarantee.
# ``tests/core/test_tenancy.py`` enumerates ``Base.registry.mappers`` and parametrizes its three
# tenancy guards over every TenantMixin model it finds, so a model no import path reaches at
# app-import time is a tenant-scoped table NOTHING checks. Other modules get this for free because
# their router imports their service, which imports their models; hospitality's router carries no
# routes until Task 6, so the import is made here rather than left as a gap for a table that
# already exists in the database.
from app.modules.hospitality import constants, models  # noqa: F401

