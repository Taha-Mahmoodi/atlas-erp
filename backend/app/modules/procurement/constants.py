"""Procurement constants (STRUCTURE §3): the vendor-master + P2P-document enums and the
permission keys, registered into the core RBAC catalog at import (D-009).

Started as a SINGLE file (STRUCTURE §8.4: split into a constants/ package only at the 400-line
cap, the finance precedent); PLAN 6.1+6.2 still sit under that.

PLAN 6.2 adds the requisition → RFQ → PO document chain and the data-driven approval-threshold
rule. The three documents carry gapless numbers claimed AT CREATION (D-040: a procurement document
is referenceable the moment it exists — a DRAFT requisition already prints a PR number that the
sourcing/ordering chain quotes — unlike finance, which numbers at posting; gaplessness still holds
because creation is the committing transaction). The approval rule is a single-characteristic
(amount) value-threshold rule per the s4hana-parity Procurement section (multi-characteristic /
multi-step release strategies are the documented later).

**Payment-terms modeling (decided here).** A vendor carries ``payment_terms_days`` — a plain
integer net-days value (30 = NET30) — NOT a separate terms master/value-set. This matches how AP
already computes a bill's due date (bill_date + net days) and keeps v1 simple; richer term
schedules (e.g. 2/10 NET30 early-payment discounts, multi-instalment plans) are deferred per the
parity doc and would arrive as a terms entity referenced from the vendor. The field is stored with
a CHECK >= 0 on the vendor.

**Vendor codes are USER-SUPPLIED and unique per tenant** (the ``UNIQUE(tenant_id, vendor_code)`` on
proc_vendors) — mirroring inventory ``item_code`` and the finance account ``code``: a vendor MASTER
carries no gapless document number (a code, not a number). The P2P DOCUMENTS in 6.2+ (requisitions,
POs, GRs) DO claim gapless numbers — a posted document in the D-012 sense — but the master does not.
"""

from enum import StrEnum

from app.core.rbac import register_permissions


class VendorStatus(StrEnum):
    """A vendor's lifecycle / usability state (parity: vendor master block levels).

    - ACTIVE: usable — new purchase orders may name this vendor (the only state 6.2+ accepts).
    - BLOCKED: temporarily barred — kept for history and existing open documents, but the P2P
      chain (6.2) refuses to raise a NEW PO against it (a soft block; the vendor can be unblocked
      back to ACTIVE).
    - INACTIVE: retired — no new business, retained for reporting and existing AP history.

    Transitions are unrestricted between the three (ACTIVE↔BLOCKED↔INACTIVE all allowed): a block
    is reversible and a retired vendor can be reactivated. The only rule the service enforces is
    that the target is a valid VendorStatus; no terminal state, because vendor history must stay
    referenceable and a mistaken retire/block must be undoable (the append-only ledger lives in
    finance AP, not here)."""

    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    INACTIVE = "INACTIVE"


# The default net-days a vendor is created with when the payload omits it (NET30 — the common
# commercial default; AP's due-date math is bill_date + this many days). Stored on the vendor.
DEFAULT_PAYMENT_TERMS_DAYS = 30


# --- P2P document status lifecycles (PLAN 6.2) --------------------------------


class RequisitionStatus(StrEnum):
    """Lifecycle of a purchase requisition — the internal "we need to buy this" request.

    - DRAFT: created, editable; lines can change. The PR number is already claimed (D-040).
    - SUBMITTED: handed off for approval. If the estimated total is AT OR ABOVE the active
      REQUISITION approval threshold the requisition STAYS here awaiting an approver; below the
      threshold the submit step auto-advances it to APPROVED (the data-driven rule).
    - APPROVED: cleared to be sourced (→ RFQ) or ordered (→ PO). Terminal-ish until converted.
    - REJECTED: an approver declined it; terminal.
    - CONVERTED: an RFQ or PO was raised from it (source_requisition_id set on the successor);
      terminal — a converted requisition is not edited or re-converted.
    - CANCELLED: abandoned before conversion (from DRAFT/SUBMITTED/APPROVED); terminal."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CONVERTED = "CONVERTED"
    CANCELLED = "CANCELLED"


class RfqStatus(StrEnum):
    """Lifecycle of a request-for-quotation. In v1 an RFQ targets ONE vendor (the vendor being
    asked to quote); multi-bidder comparison is the documented parity later.

    - DRAFT: created, editable.
    - SENT: issued to the vendor (DRAFT→SENT).
    - QUOTED: the vendor's prices have been recorded onto the lines (SENT→QUOTED).
    - CLOSED: sourcing finished (a PO was raised, or the RFQ is shelved); terminal-ish.
    - CANCELLED: abandoned; terminal."""

    DRAFT = "DRAFT"
    SENT = "SENT"
    QUOTED = "QUOTED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class PurchaseOrderStatus(StrEnum):
    """Lifecycle of a purchase order — the committing P2P document.

    States SET in 6.2: DRAFT, PENDING_APPROVAL, APPROVED, REJECTED, SENT, CANCELLED.
    States driven by 6.3 GOODS RECEIPTS (declared now as the lifecycle, but the transitions INTO
    them land in 6.3): PARTIALLY_RECEIVED, RECEIVED, CLOSED.

    - DRAFT: created, editable; PO number already claimed (D-040). Lines validated (vendor ACTIVE,
      every item APPROVED for the vendor).
    - PENDING_APPROVAL: a SEND was attempted and the total is AT OR ABOVE the active PURCHASE_ORDER
      approval threshold — awaiting an approver (requires procurement.po.approve).
    - APPROVED: cleared to be sent (below threshold ⇒ the send auto-approves straight to here).
    - REJECTED: an approver declined; terminal.
    - SENT: issued to the vendor — the commitment is live; only an APPROVED PO may be SENT.
    - PARTIALLY_RECEIVED / RECEIVED: set by 6.3 as goods receipts post against the lines
      (received_quantity rises); RECEIVED when every line is fully received.
    - CLOSED: fully received + billed (6.4) or short-closed; terminal.
    - CANCELLED: abandoned before any receipt; terminal (6.3 forbids cancelling a received PO)."""

    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SENT = "SENT"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ApprovalDecision(StrEnum):
    """An approver's verdict on a submitted requisition / pending PO (the approve/reject action)."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalDocumentType(StrEnum):
    """Which document kind an approval rule governs (PLAN 6.2). One active rule per (tenant,
    document_type): the REQUISITION rule gates submit; the PURCHASE_ORDER rule gates send."""

    REQUISITION = "REQUISITION"
    PURCHASE_ORDER = "PURCHASE_ORDER"


# --- Document types + number sequences (D-012/D-040) --------------------------
# The three P2P documents each register in core_documents and claim a gapless number AT CREATION
# (D-040: claim-at-creation so the document is referenceable immediately; the orders/receipts
# claim-timing branch, not finance's draft-numbered-at-post branch). Sequences year-reset
# (PR-2026-00001 / RFQ-2026-00001 / PO-2026-00001).
REQUISITION_DOC_TYPE = "procurement.requisition"
REQUISITION_SEQUENCE_NAME = "procurement.requisition"
REQUISITION_NUMBER_PREFIX = "PR"
REQUISITION_NUMBER_PADDING = 5

RFQ_DOC_TYPE = "procurement.rfq"
RFQ_SEQUENCE_NAME = "procurement.rfq"
RFQ_NUMBER_PREFIX = "RFQ"
RFQ_NUMBER_PADDING = 5

PURCHASE_ORDER_DOC_TYPE = "procurement.purchase_order"
PURCHASE_ORDER_SEQUENCE_NAME = "procurement.po"
PURCHASE_ORDER_NUMBER_PREFIX = "PO"
PURCHASE_ORDER_NUMBER_PADDING = 5

# docflow link types joining the chain (D-012 vocabulary). The edge is predecessor → successor, so
# the link_type names the edge from the predecessor's point of view:
#   requisition → rfq : the requisition is "sourced_by" the RFQ.
#   rfq → po          : the RFQ is "ordered_by" the PO.
#   requisition → po  : a requisition converted straight to a PO is "ordered_by" it too.
REQUISITION_SOURCED_BY_RFQ_LINK = "sourced_by"
RFQ_ORDERED_BY_PO_LINK = "ordered_by"
REQUISITION_ORDERED_BY_PO_LINK = "ordered_by"


# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Vendor master (PLAN 6.1): read the vendor master (+ its approved items) vs create/edit it.
# Approved-item management rides VENDOR_MANAGE (the inventory item/uom-conversion precedent: nested
# config shares the parent's manage key).
PROCUREMENT_VENDOR_READ = "procurement.vendor.read"
PROCUREMENT_VENDOR_MANAGE = "procurement.vendor.manage"
# Requisitions (PLAN 6.2): read vs create/edit/submit/convert vs the privileged APPROVE action
# (approving a submitted requisition is a distinct authority — the journal.post precedent).
PROCUREMENT_REQUISITION_READ = "procurement.requisition.read"
PROCUREMENT_REQUISITION_MANAGE = "procurement.requisition.manage"
PROCUREMENT_REQUISITION_APPROVE = "procurement.requisition.approve"
# RFQs (PLAN 6.2): read vs create/edit/send/record-quote/convert. No separate approve key — an RFQ
# carries no approval gate (sourcing is not a committing action; the PO is).
PROCUREMENT_RFQ_READ = "procurement.rfq.read"
PROCUREMENT_RFQ_MANAGE = "procurement.rfq.manage"
# Purchase orders (PLAN 6.2): read vs create/edit/convert/send vs the privileged APPROVE action
# (approving a pending-approval PO commits spend — its own key).
PROCUREMENT_PO_READ = "procurement.po.read"
PROCUREMENT_PO_MANAGE = "procurement.po.manage"
PROCUREMENT_PO_APPROVE = "procurement.po.approve"
# Approval rules (PLAN 6.2): managing the value thresholds is a single config authority.
PROCUREMENT_APPROVAL_RULE_MANAGE = "procurement.approval_rule.manage"

register_permissions(
    PROCUREMENT_VENDOR_READ,
    PROCUREMENT_VENDOR_MANAGE,
    PROCUREMENT_REQUISITION_READ,
    PROCUREMENT_REQUISITION_MANAGE,
    PROCUREMENT_REQUISITION_APPROVE,
    PROCUREMENT_RFQ_READ,
    PROCUREMENT_RFQ_MANAGE,
    PROCUREMENT_PO_READ,
    PROCUREMENT_PO_MANAGE,
    PROCUREMENT_PO_APPROVE,
    PROCUREMENT_APPROVAL_RULE_MANAGE,
    descriptions={
        PROCUREMENT_VENDOR_READ: "Read vendors and their approved items",
        PROCUREMENT_VENDOR_MANAGE: "Create and edit vendors and their approved items",
        PROCUREMENT_REQUISITION_READ: "Read purchase requisitions",
        PROCUREMENT_REQUISITION_MANAGE: "Create, edit, submit and convert purchase requisitions",
        PROCUREMENT_REQUISITION_APPROVE: "Approve or reject submitted purchase requisitions",
        PROCUREMENT_RFQ_READ: "Read requests for quotation",
        PROCUREMENT_RFQ_MANAGE: "Create, edit, send, quote and convert requests for quotation",
        PROCUREMENT_PO_READ: "Read purchase orders",
        PROCUREMENT_PO_MANAGE: "Create, edit, convert and send purchase orders",
        PROCUREMENT_PO_APPROVE: "Approve or reject purchase orders pending approval",
        PROCUREMENT_APPROVAL_RULE_MANAGE: "Manage procurement approval-threshold rules",
    },
)
