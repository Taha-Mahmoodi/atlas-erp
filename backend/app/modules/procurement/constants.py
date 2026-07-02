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


class GoodsReceiptStatus(StrEnum):
    """Lifecycle of a goods receipt — the document recording physical receipt of PO goods (6.3).

    DRAFT → POSTED (chosen over post-at-create), because a GR is a document a receiving clerk
    BUILDS line-by-line (which PO lines, into which bins, how much, lot/serials) and THEN posts: at
    POST the stock RECEIPT moves are created (Dr Inventory / Cr GR-IR), the PO's received_quantity
    rises and its status advances. Unlike a stock move (permanent at creation), a GR has a genuine
    editable build phase, so DRAFT→POSTED is the right shape.

    - DRAFT: created, editable; the GR number is already claimed (D-040 claim-at-creation). No stock
      has moved, the PO is untouched. Can be CANCELLED.
    - POSTED: the receipt is committed — N stock RECEIPT moves exist, the inventory-debit / GR-IR
      journals are posted, the PO lines' received_quantity is raised and the PO status advanced. The
      whole post is ONE transaction (GR + moves + journals + PO update) — all-or-nothing (a closed
      period or insufficient handler rolls it ALL back). TERMINAL: a POSTED GR is corrected by a
      reversing GR / a return (Phase 7 RMA), never cancelled (v1 has no reverse-GR; documented).
    - CANCELLED: a DRAFT abandoned before posting; terminal. No stock ever moved."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class MatchStatus(StrEnum):
    """Lifecycle of a 3-way invoice match — the procure-to-pay closing document (PLAN 6.4, D-042).

    A match compares a vendor's invoice against the PO (price) and the goods receipt (quantity);
    on POST it triggers the AP vendor bill (Dr GR/IR + PPV / Cr AP) that clears the GR/IR account
    the goods receipt credited at receipt.

    - DRAFT: created, editable; the MATCH number is already claimed (D-040 claim-at-creation). No
      bill yet. Can be CANCELLED.
    - MATCHED: every line is within tolerance (price within X%, quantity exact against receipt) —
      the match is clean and may be POSTed.
    - EXCEPTION: at least one line exceeds the price tolerance — the match is BLOCKED from posting
      until an authorized user OVERRIDEs it (the invoice-release control); override moves it to
      MATCHED. A clerk cannot silently bill a price the buyer did not agree to.
    - POSTED: the AP vendor bill was created + posted (Dr GR/IR / Cr AP, PPV for the price
      variance), the PO billed_quantity was raised and the PO advanced toward CLOSED — ONE
      transaction.
      TERMINAL: corrected by a credit memo / reversal (Phase 7), never re-posted.
    - CANCELLED: a DRAFT/EXCEPTION abandoned before posting; terminal. No bill ever created."""

    DRAFT = "DRAFT"
    MATCHED = "MATCHED"
    EXCEPTION = "EXCEPTION"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


# Per-tenant 3-way-match tolerances (PLAN 6.4, D-042). A `proc_match_tolerances` row (single active
# row per tenant in v1 — the ApprovalRule single-per-tenant precedent; per-vendor tolerance groups
# are the documented later) holds the price + quantity tolerance PERCENTAGES. A line's invoiced unit
# price within `price_tolerance_percent` of the PO price → within tolerance; over it → EXCEPTION.
# These DEFAULTS apply when a tenant has not configured a row (the no-rule-runs-loose precedent of
# the approval threshold): 0% price tolerance means any price difference is an exception by default,
# so a tenant must opt into a band — chosen STRICT (a price change should be a deliberate decision).
DEFAULT_PRICE_TOLERANCE_PERCENT = 0
DEFAULT_QUANTITY_TOLERANCE_PERCENT = 0


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

# Goods receipt (PLAN 6.3): registers in core_documents + claims a gapless GR number AT CREATION
# (D-040, claim-at-creation; year-resetting GR-2026-00001), the orders/receipts branch.
GOODS_RECEIPT_DOC_TYPE = "procurement.goods_receipt"
GOODS_RECEIPT_SEQUENCE_NAME = "procurement.goods_receipt"
GOODS_RECEIPT_NUMBER_PREFIX = "GR"
GOODS_RECEIPT_NUMBER_PADDING = 5

# Invoice match (PLAN 6.4, D-042): the 3-way-match document. Registers in core_documents + claims a
# gapless MATCH number AT CREATION (D-040; year-resetting MATCH-2026-00001). This is the MATCH
# document number — the finance vendor bill the match triggers claims its OWN BILL- number.
INVOICE_MATCH_DOC_TYPE = "procurement.invoice_match"
INVOICE_MATCH_SEQUENCE_NAME = "procurement.invoice_match"
INVOICE_MATCH_NUMBER_PREFIX = "MATCH"
INVOICE_MATCH_NUMBER_PADDING = 5

# docflow link types joining the chain (D-012 vocabulary). The edge is predecessor → successor, so
# the link_type names the edge from the predecessor's point of view:
#   requisition → rfq : the requisition is "sourced_by" the RFQ.
#   rfq → po          : the RFQ is "ordered_by" the PO.
#   requisition → po  : a requisition converted straight to a PO is "ordered_by" it too.
REQUISITION_SOURCED_BY_RFQ_LINK = "sourced_by"
RFQ_ORDERED_BY_PO_LINK = "ordered_by"
REQUISITION_ORDERED_BY_PO_LINK = "ordered_by"
# Goods-receipt edges (PLAN 6.3, D-041): the PO is "received_by" the GR; the GR "moved_by" each
# stock move it generated (the GR↔move linkage lives in docflow, NOT a cross-module FK — D-041).
PO_RECEIVED_BY_GR_LINK = "received_by"
GR_MOVED_BY_STOCK_MOVE_LINK = "moved_by"

# Invoice-match edges (PLAN 6.4, D-042): the PO is "matched_by" the match; each GR feeding the match
# is "matched_by" it too; the match is "billed_by" the finance vendor bill it triggers. The match→
# bill link spans into FINANCE's document (the AP-bill-posts-link precedent) — written by finance's
# handler when it posts the bill, so procurement records no cross-module FK into the bill table.
PO_MATCHED_BY_INVOICE_MATCH_LINK = "matched_by"
GR_MATCHED_BY_INVOICE_MATCH_LINK = "matched_by"
INVOICE_MATCH_BILLED_BY_BILL_LINK = "billed_by"

# The procurement domain event the goods-receipt POST publishes (D-011/D-041): inventory's
# handlers.py subscribes and creates the stock RECEIPT moves with the GR/IR offset in the SAME
# transaction (the sanctioned cross-module mechanism — procurement never imports inventory/service).
GOODS_RECEIPT_POSTED_EVENT_KEY = "procurement.goods_receipt.posted"

# The procurement domain event the invoice-match POST publishes (D-011/D-042): finance's handlers.py
# subscribes and creates+posts the AP vendor bill (Dr GR/IR + PPV / Cr AP) in the SAME transaction
# (the sanctioned cross-module mechanism — procurement never imports finance/service; it publishes
# the event and finance handles its OWN bill posting). Mirrors the GR→inventory bridge of 6.3.
INVOICE_MATCHED_EVENT_KEY = "procurement.invoice_match.matched"


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
# Goods receipts (PLAN 6.3): read vs create/edit/cancel the draft document vs the privileged POST
# action (posting a GR creates stock + posts the GR/IR journal — its own authority, the journal.post
# precedent: building a document and committing it are distinct rights).
PROCUREMENT_GOODS_RECEIPT_READ = "procurement.goods_receipt.read"
PROCUREMENT_GOODS_RECEIPT_MANAGE = "procurement.goods_receipt.manage"
PROCUREMENT_GOODS_RECEIPT_POST = "procurement.goods_receipt.post"
# Invoice matches (PLAN 6.4): read vs create/edit/override/cancel the match vs the privileged POST
# action (posting a match creates + posts the AP vendor bill via the event bus — its own authority,
# the journal.post / goods_receipt.post precedent: building a document and committing it are
# distinct rights). The OVERRIDE of an EXCEPTION rides MANAGE — clearing a price exception is the
# manager's call, recorded in the audit trail (a future tenant may split it to its own key).
PROCUREMENT_INVOICE_MATCH_READ = "procurement.invoice_match.read"
PROCUREMENT_INVOICE_MATCH_MANAGE = "procurement.invoice_match.manage"
PROCUREMENT_INVOICE_MATCH_POST = "procurement.invoice_match.post"

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
    PROCUREMENT_GOODS_RECEIPT_READ,
    PROCUREMENT_GOODS_RECEIPT_MANAGE,
    PROCUREMENT_GOODS_RECEIPT_POST,
    PROCUREMENT_INVOICE_MATCH_READ,
    PROCUREMENT_INVOICE_MATCH_MANAGE,
    PROCUREMENT_INVOICE_MATCH_POST,
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
        PROCUREMENT_GOODS_RECEIPT_READ: "Read goods receipts",
        PROCUREMENT_GOODS_RECEIPT_MANAGE: "Create, edit and cancel draft goods receipts",
        PROCUREMENT_GOODS_RECEIPT_POST: "Post goods receipts (move stock and post the GR/IR entry)",
        PROCUREMENT_INVOICE_MATCH_READ: "Read 3-way invoice matches",
        PROCUREMENT_INVOICE_MATCH_MANAGE: "Create, override and cancel invoice matches",
        PROCUREMENT_INVOICE_MATCH_POST: "Post invoice matches (create and post the AP vendor bill)",
    },
)
