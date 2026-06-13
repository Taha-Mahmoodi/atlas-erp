"""Manufacturing constants (STRUCTURE §3): the BOM/routing status enums and the permission keys,
registered into the core RBAC catalog at import (D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap, the
inventory precedent) — PLAN 8.1's masters sit well under that. Production orders (8.2) and MRP (8.3)
will add their own document types / number sequences / event keys; if that pushes this past the cap
it becomes a constants/ package then, the sales precedent.

IDENTITY + NUMBERING (decided here, D-047). Manufacturing MASTERS carry no gapless document number:

- **Work centres** and the BOM/routing CODE-bearing identity follow the master-data precedent
  (item_code / vendor_code / customer_code): ``work_center_code`` is USER-SUPPLIED and unique per
  tenant (``UNIQUE(tenant_id, code)``). A code, not a gapless number.
- **A BOM is identified by ``(item_id, version)``** — the item it PRODUCES plus a user-supplied
  version string — NOT a standalone code, mirroring S/4HANA's "BOM is keyed by material + BOM
  usage/alternative". ``UNIQUE(tenant_id, item_id, version)``. The same shape is used for routings
  for consistency: a routing is ``(item_id, version)`` too (NOT a routing_code), so BOM and routing
  identity read identically and a routing can be looked up the same way a BOM is.

There is deliberately NO auto-sequence here: a master carries a stable user-chosen handle, never a
gapless number. The PRODUCTION ORDERS in 8.2 WILL register documents and claim a gapless number (a
posted document in the D-012 sense) — but the masters do not.

ACTIVATION MODEL (D-047). A BOM/routing version has a lifecycle status (DRAFT|ACTIVE|INACTIVE):

- **DRAFT** — editable: components/operations may be added, changed and removed. A new version is
  born DRAFT.
- **ACTIVE** — usable by production/MRP and FROZEN: its components/operations can no longer be
  changed (corrections are a NEW version, the append-only-master philosophy). At most ONE
  ACTIVE+``is_default`` version per item — the one ``get_active_bom_for_item`` /
  ``get_active_routing_for_item`` resolve (8.2/8.3 read this). Activating a version that becomes the
  new default first demotes the previously-default ACTIVE version's ``is_default`` flag.
- **INACTIVE** — retired: a once-ACTIVE version superseded by a newer one; kept for history /
  referenceability, never deleted.

"MULTI-LEVEL via references" (D-047). The SCHEMA is single-level-per-BOM: a ``Bom`` header lists the
DIRECT components of one parent item. "Multi-level" emerges because a component item can itself be
the parent of its OWN ``Bom`` — the tree is resolved by EXPLOSION at MRP time (8.3), which walks
component item -> its active BOM -> its components recursively. A direct self-component (a component
whose item IS the BOM's parent) is rejected at the masters here; deeper cycle prevention (A needs B
needs A) is a 8.3 explosion-time concern (the explosion carries a visited set + depth cap, the
docflow get_chain precedent), not enforceable on a single-level row.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class ProductionOrderStatus(StrEnum):
    """Lifecycle of a PRODUCTION ORDER (PLAN 8.2, D-048). A production order turns components into a
    finished parent item; its status tracks the issue→finish progress.

    Transitions (the service owns them, CLAUDE.md rule 7):

    - **DRAFT** — created + the active BOM EXPLODED into reserved component rows (and the routing
      snapshotted into order operations). Editable only via cancel; releasing moves it forward.
    - **RELEASED** — materials are reserved (the component rows ARE the reservation, v1 ATP-style —
      release does NOT block on availability, only optionally flags shortages). Ready to issue.
    - **IN_PROGRESS** — at least one component has been issued to WIP (Dr WIP / Cr Inventory). The
      order is mid-production: it can issue more components or finish.
    - **FINISHED** — the parent item has been fully produced to stock (Dr Inventory / Cr WIP) and
      the ordered quantity is met. Terminal; WIP nets to zero (issue debits = finished credit +
      variance flush).
    - **CANCELLED** — abandoned before any component issued (DRAFT/RELEASED only). Once components
      are issued the order is POSTED-ish: it must be FINISHED (a future phase adds reversal), never
      cancelled, so issued stock + WIP never strand. Terminal.
    """

    DRAFT = "DRAFT"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class BomStatus(StrEnum):
    """Lifecycle of a BOM VERSION (D-047). A BOM is activated to become usable by production/MRP.

    - DRAFT: editable — components may be added/changed/removed. A new version starts here.
    - ACTIVE: usable by 8.2/8.3 and FROZEN — components are immutable; at most one ACTIVE+default
      version per item (the one MRP/production resolve).
    - INACTIVE: retired — a superseded version, kept for history, never deleted.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class RoutingStatus(StrEnum):
    """Lifecycle of a ROUTING VERSION (D-047) — the routing twin of ``BomStatus``, identical
    semantics so BOM and routing activation read the same:

    - DRAFT: editable — operations may be added/changed/removed.
    - ACTIVE: usable by 8.2/8.3 and FROZEN — operations are immutable; at most one ACTIVE+default
      version per item.
    - INACTIVE: retired — kept for history, never deleted.
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# read vs manage on each of the three masters. "manage" covers create/edit/activate/deactivate —
# activation is part of authoring a BOM/routing, not a separate privileged posting like
# journal.post (a BOM activation drives no GL effect), so it rides the manage key rather than its
# own. A separate key can be carved out later if activation needs segregation-of-duties.
MFG_BOM_READ = "manufacturing.bom.read"
MFG_BOM_MANAGE = "manufacturing.bom.manage"
MFG_WORKCENTER_READ = "manufacturing.workcenter.read"
MFG_WORKCENTER_MANAGE = "manufacturing.workcenter.manage"
MFG_ROUTING_READ = "manufacturing.routing.read"
MFG_ROUTING_MANAGE = "manufacturing.routing.manage"

# Production-order permissions (PLAN 8.2, D-048). Three authorities at a sensible granularity:
# - ``.manage`` — create+explode, edit (cancel a draft) the order document (the masters' manage
#   precedent; no GL effect, like a delivery DRAFT).
# - ``.release`` — reserve materials (DRAFT→RELEASED). A distinct authority because committing
#   capacity/material is a planning decision separate from authoring the order.
# - ``.execute`` — issue components (Dr WIP / Cr Inventory) AND finish to stock (Dr Inventory / Cr
#   WIP). Issue + finish are folded under ONE key (both POST stock + journals — the shop-floor
#   action), the way a delivery's stock-issuing post is one ``.post`` right; segregating issue from
#   finish further is a later if a tenant needs it.
MFG_PRODUCTION_ORDER_READ = "manufacturing.production_order.read"
MFG_PRODUCTION_ORDER_MANAGE = "manufacturing.production_order.manage"
MFG_PRODUCTION_ORDER_RELEASE = "manufacturing.production_order.release"
MFG_PRODUCTION_ORDER_EXECUTE = "manufacturing.production_order.execute"

register_permissions(
    MFG_BOM_READ,
    MFG_BOM_MANAGE,
    MFG_WORKCENTER_READ,
    MFG_WORKCENTER_MANAGE,
    MFG_ROUTING_READ,
    MFG_ROUTING_MANAGE,
    MFG_PRODUCTION_ORDER_READ,
    MFG_PRODUCTION_ORDER_MANAGE,
    MFG_PRODUCTION_ORDER_RELEASE,
    MFG_PRODUCTION_ORDER_EXECUTE,
    descriptions={
        MFG_BOM_READ: "Read bills of materials and their components",
        MFG_BOM_MANAGE: "Create, edit and activate bills of materials and their components",
        MFG_WORKCENTER_READ: "Read work centres",
        MFG_WORKCENTER_MANAGE: "Create and edit work centres",
        MFG_ROUTING_READ: "Read routings and their operations",
        MFG_ROUTING_MANAGE: "Create, edit and activate routings and their operations",
        MFG_PRODUCTION_ORDER_READ: "Read production orders and their components",
        MFG_PRODUCTION_ORDER_MANAGE: "Create, edit and cancel production orders",
        MFG_PRODUCTION_ORDER_RELEASE: "Release production orders (reserve materials)",
        MFG_PRODUCTION_ORDER_EXECUTE: "Issue components to and finish production orders",
    },
)

# --- Production-order document type, numbering + docflow links (PLAN 8.2, D-048) ---------------
# A production order IS a posted document in the D-012 sense (it registers in core_documents and
# claims a gapless number at creation, the orders/deliveries precedent — unlike the 8.1 masters,
# which carry no number). The prefix is "MO-" (Manufacturing Order): "PRO-" was an alternative but
# "PO-" is already the PURCHASE-order prefix, so a distinct, unambiguous "MO-" avoids any clash.
PRODUCTION_ORDER_DOC_TYPE = "manufacturing.production_order"
PRODUCTION_ORDER_SEQUENCE_NAME = "manufacturing.production_order"
PRODUCTION_ORDER_NUMBER_PREFIX = "MO"
PRODUCTION_ORDER_NUMBER_PADDING = 5

# Docflow edges from a production order to its downstream stock moves (D-012/D-048). The component
# ISSUE moves and the finished RECEIPT move are inventory documents; manufacturing's flow PUBLISHES
# the events and inventory's handler writes these edges (production order → 'issued_to' → ISSUE
# move; production order → 'finished_to' → RECEIPT move), as the GR/delivery handlers write their
# 'moved_by' edges. A future MRP link (sales order → 'planned_by' → production order) is reserved.
PRODUCTION_ORDER_ISSUED_TO_MOVE_LINK = "issued_to"
PRODUCTION_ORDER_FINISHED_TO_MOVE_LINK = "finished_to"

# Event keys (D-011/D-048) — the SANCTIONED cross-module mechanism (STRUCTURE §5): manufacturing
# PUBLISHES, inventory's handlers create the moves with the WIP offset override.
COMPONENTS_ISSUED_EVENT_KEY = "manufacturing.production_order.components_issued"
ORDER_FINISHED_EVENT_KEY = "manufacturing.production_order.finished"
