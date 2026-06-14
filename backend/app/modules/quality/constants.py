"""Quality constants (STRUCTURE §3): the inspection-lot enums + permission keys + the document
type / number sequence / event key / docflow links, registered into the core RBAC catalog at import
(D-009).

A SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line cap) — PLAN
9.1's small QM core sits well under that.

IDENTITY + NUMBERING (D-050). An inspection LOT IS a posted document in the D-012 sense: it
registers
in core_documents and claims a gapless ``QL-`` number at the moment it is created (the GR handler
creates it OPEN, the orders/receipts claim-at-creation branch — it is permanent at creation, not a
draft). The prefix is "QL" (Quality Lot); "INSP-" was an alternative but "QL-" is shorter and
unambiguous against the other module prefixes (PO-/GR-/SO-/DN-/MO-/MRP-).

SCOPE (s4hana-parity §QM, D-050). v1 is binary accept/reject with a stock move — no inspection
plans,
no characteristics, no results recording, no usage-decision code catalogs, no quality notifications.
The lot is plan-less: it records the inspected quantity and a lot-level accept/reject outcome only.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class InspectionLotStatus(StrEnum):
    """Lifecycle of an INSPECTION LOT (PLAN 9.1, D-050). A lot is created OPEN when a goods receipt
    with ``requires_inspection`` posts; a usage DECISION accepts/rejects it.

    Transitions (the service owns them, CLAUDE.md rule 7):

    - **OPEN** — created by the GR handler the moment a flagged GR line posts. The received stock is
      already on hand (a v1 inspection lot does NOT block use — there is no separate
      quality-inspection stock bucket); the lot records what must be decided. A usage decision moves
      it forward; a cancel discards it.
    - **ACCEPTED** — the usage decision accepted the WHOLE lot (rejected_quantity == 0). No stock
      move: the accepted stock is already received and usable. Terminal.
    - **REJECTED** — the usage decision rejected SOME OR ALL of the lot (rejected_quantity > 0). The
      rejected quantity is dispositioned via the event bus (SCRAP write-off / BLOCK transfer); the
      accepted remainder (if any) stays put. ``accepted_quantity``/``rejected_quantity`` record the
      split. Terminal. (v1 has no PARTIALLY_ACCEPTED status — any rejection lands REJECTED with both
      quantities recorded, D-050.)
    - **CANCELLED** — an OPEN lot discarded with no decision (a flagged GR posted in error, the lot
      is moot). Terminal; moves no stock.
    """

    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class InspectionSource(StrEnum):
    """Where an inspection lot ORIGINATED (PLAN 9.1, D-050). The enum is declared with room for the
    parity-doc's later lot origins (production / delivery / manual), but v1 creates lots from
    exactly
    ONE source — a goods receipt's inspection flag.

    - **GOODS_RECEIPT** — the only v1 source: a posted GR line with ``requires_inspection=True``
      auto-creates the lot via the event handler.
    """

    GOODS_RECEIPT = "GOODS_RECEIPT"


class RejectDisposition(StrEnum):
    """What happens to REJECTED stock on a usage decision (PLAN 9.1, D-050). v1 implements SCRAP and
    BLOCK; RETURN_TO_VENDOR is declared for the catalog but NOT implemented (it needs a
    vendor-return
    chain — parity-doc "later"; selecting it is rejected 422).

    - **SCRAP** — the rejected stock is written off: inventory performs an ADJUSTMENT-out from the
      receiving bin, and the costing engine posts the write-off journal (Dr inventory-adjustment /
      price-difference, Cr Inventory) at the stock's book value. Total on-hand DROPS by the rejected
      quantity.
    - **BLOCK** — the rejected stock is quarantined: inventory performs a TRANSFER from the
    receiving
      bin to the tenant's designated BLOCKED/QI bin. Value-neutral (no journal); total on-hand is
      UNCHANGED, but the stock leaves the usable bin.
    - **RETURN_TO_VENDOR** — declared, NOT implemented in v1 (the vendor-return/credit chain is a
      later, per s4hana-parity §RMA). Choosing it on a decision is a 422.
    """

    SCRAP = "SCRAP"
    BLOCK = "BLOCK"
    RETURN_TO_VENDOR = "RETURN_TO_VENDOR"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# read vs manage vs decide. ``.decide`` (the accept/reject usage decision) is DISTINCT from
# ``.manage`` because a usage decision moves stock + posts a write-off journal (a privileged
# posting,
# the journal.post / delivery.post precedent), whereas ``.manage`` only cancels an OPEN lot (no GL
# effect). The GR handler creates lots with no permission check (it runs in the GR post's
# transaction, already authorised as a procurement action) — so there is no ``.create`` key.
QUALITY_INSPECTION_READ = "quality.inspection.read"
QUALITY_INSPECTION_MANAGE = "quality.inspection.manage"
QUALITY_INSPECTION_DECIDE = "quality.inspection.decide"

register_permissions(
    QUALITY_INSPECTION_READ,
    QUALITY_INSPECTION_MANAGE,
    QUALITY_INSPECTION_DECIDE,
    descriptions={
        QUALITY_INSPECTION_READ: "Read inspection lots",
        QUALITY_INSPECTION_MANAGE: "Cancel open inspection lots",
        QUALITY_INSPECTION_DECIDE: "Decide (accept/reject) inspection lots",
    },
)

# --- Inspection-lot document type, numbering + docflow links (PLAN 9.1, D-050) ---------------
# An inspection lot IS a posted document in the D-012 sense (it registers in core_documents and
# claims a gapless number at creation — the orders/receipts precedent). The prefix is "QL-"
# (Quality Lot), distinct from every other module prefix.
INSPECTION_LOT_DOC_TYPE = "quality.inspection_lot"
INSPECTION_LOT_SEQUENCE_NAME = "quality.inspection_lot"
INSPECTION_LOT_NUMBER_PREFIX = "QL"
INSPECTION_LOT_NUMBER_PADDING = 5

# Docflow edges (D-012/D-050): the goods-receipt document → 'inspected_by' → inspection-lot document
# (the GR handler writes it when it creates the lot), and the inspection-lot document →
# 'dispositioned_by' → the disposition stock-move document (inventory's handler writes it when it
# moves the rejected stock, the GR/delivery 'moved_by' precedent — quality publishes the event,
# inventory writes the edge from its side because it owns the move).
GR_INSPECTED_BY_LOT_LINK = "inspected_by"
INSPECTION_DISPOSITIONED_BY_MOVE_LINK = "dispositioned_by"

# Event key (D-011/D-050) — the SANCTIONED cross-module mechanism (STRUCTURE §5): a REJECT usage
# decision PUBLISHES this; inventory's handler creates the disposition stock move (SCRAP = an
# ADJUSTMENT-out write-off; BLOCK = a TRANSFER to the blocked bin). Quality never imports inventory
# service. (An ACCEPT publishes nothing — the accepted stock is already received and usable.)
INSPECTION_DISPOSITIONED_EVENT_KEY = "quality.inspection_lot.dispositioned"
