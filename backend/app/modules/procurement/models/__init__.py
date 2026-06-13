"""Procurement models package (STRUCTURE §3: split into a models/ package at the 400-line cap when
PLAN 6.2's requisition/RFQ/PO/approval-rule tables landed, the finance/inventory precedent).

Re-exports every model so ``from app.modules.procurement.models import Vendor`` (and
``PurchaseOrder``, ``Rfq``, ...) keep working from ONE surface, and so every importer (alembic
env.py, the tenancy mapper-enumeration suite) registers all tables on ``Base.metadata``.

- ``vendors``: the vendor master + the v1 approved-items info-record-lite (6.1).
- ``requisitions``: the purchase-requisition header + lines (6.2) — the first P2P document.
- ``rfqs``: the request-for-quotation header + lines (6.2) — the sourcing document.
- ``orders``: the purchase-order header + lines (6.2) — the committing document.
- ``goods_receipts``: the goods-receipt header + lines (6.3) — receipt of PO goods → stock + GR/IR.
- ``approvals``: the value-threshold approval rule that gates requisition submit + PO send (6.2).
"""

from app.modules.procurement.models.approvals import ApprovalRule
from app.modules.procurement.models.goods_receipts import GoodsReceipt, GoodsReceiptLine
from app.modules.procurement.models.orders import PurchaseOrder, PurchaseOrderLine
from app.modules.procurement.models.requisitions import (
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from app.modules.procurement.models.rfqs import Rfq, RfqLine
from app.modules.procurement.models.vendors import Vendor, VendorApprovedItem

__all__ = [
    "ApprovalRule",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "PurchaseRequisition",
    "PurchaseRequisitionLine",
    "Rfq",
    "RfqLine",
    "Vendor",
    "VendorApprovedItem",
]
