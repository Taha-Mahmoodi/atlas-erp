"""Procurement schemas package (STRUCTURE §3: split at the 400-line cap when PLAN 6.2's
requisition/RFQ/PO/approval-rule schemas landed). Re-exports every schema so
``from app.modules.procurement.schemas import VendorCreate`` (and the P2P document schemas) keep
working from ONE surface.

- ``vendors``: vendor master + approved-item schemas (6.1).
- ``requisitions``: requisition header/line + submit/approve action payloads (6.2).
- ``rfqs``: RFQ header/line + record-quote / convert-from-requisition payloads (6.2).
- ``orders``: PO header/line + convert-from-requisition / convert-from-RFQ payloads (6.2).
- ``goods_receipts``: goods-receipt header/line + filter schemas (6.3).
- ``approvals``: value-threshold approval-rule schemas (6.2).
"""

from app.modules.procurement.schemas.approvals import (
    ApprovalRuleCreate,
    ApprovalRuleFilter,
    ApprovalRuleRead,
    ApprovalRuleUpdate,
)
from app.modules.procurement.schemas.goods_receipts import (
    GoodsReceiptCreate,
    GoodsReceiptDetail,
    GoodsReceiptFilter,
    GoodsReceiptLineCreate,
    GoodsReceiptLineRead,
    GoodsReceiptRead,
)
from app.modules.procurement.schemas.invoice_matches import (
    InvoiceMatchCreate,
    InvoiceMatchDetail,
    InvoiceMatchFilter,
    InvoiceMatchLineCreate,
    InvoiceMatchLineRead,
    InvoiceMatchRead,
    MatchToleranceRead,
    MatchToleranceUpsert,
)
from app.modules.procurement.schemas.orders import (
    PurchaseOrderCreate,
    PurchaseOrderDetail,
    PurchaseOrderFilter,
    PurchaseOrderFromRequisition,
    PurchaseOrderFromRfq,
    PurchaseOrderLineCreate,
    PurchaseOrderLineRead,
    PurchaseOrderRead,
)
from app.modules.procurement.schemas.requisitions import (
    ApprovalDecisionPayload,
    RequisitionCreate,
    RequisitionDetail,
    RequisitionFilter,
    RequisitionLineCreate,
    RequisitionLineRead,
    RequisitionRead,
    RequisitionUpdate,
)
from app.modules.procurement.schemas.rfqs import (
    RecordQuotePayload,
    RfqCreate,
    RfqDetail,
    RfqFilter,
    RfqFromRequisition,
    RfqLineCreate,
    RfqLineQuote,
    RfqLineRead,
    RfqRead,
)
from app.modules.procurement.schemas.vendors import (
    VendorApprovedItemCreate,
    VendorApprovedItemRead,
    VendorCreate,
    VendorFilter,
    VendorRead,
    VendorUpdate,
)

__all__ = [
    "ApprovalDecisionPayload",
    "ApprovalRuleCreate",
    "ApprovalRuleFilter",
    "ApprovalRuleRead",
    "ApprovalRuleUpdate",
    "GoodsReceiptCreate",
    "GoodsReceiptDetail",
    "GoodsReceiptFilter",
    "GoodsReceiptLineCreate",
    "GoodsReceiptLineRead",
    "GoodsReceiptRead",
    "InvoiceMatchCreate",
    "InvoiceMatchDetail",
    "InvoiceMatchFilter",
    "InvoiceMatchLineCreate",
    "InvoiceMatchLineRead",
    "InvoiceMatchRead",
    "MatchToleranceRead",
    "MatchToleranceUpsert",
    "PurchaseOrderCreate",
    "PurchaseOrderDetail",
    "PurchaseOrderFilter",
    "PurchaseOrderFromRequisition",
    "PurchaseOrderFromRfq",
    "PurchaseOrderLineCreate",
    "PurchaseOrderLineRead",
    "PurchaseOrderRead",
    "RecordQuotePayload",
    "RequisitionCreate",
    "RequisitionDetail",
    "RequisitionFilter",
    "RequisitionLineCreate",
    "RequisitionLineRead",
    "RequisitionRead",
    "RequisitionUpdate",
    "RfqCreate",
    "RfqDetail",
    "RfqFilter",
    "RfqFromRequisition",
    "RfqLineCreate",
    "RfqLineQuote",
    "RfqLineRead",
    "RfqRead",
    "VendorApprovedItemCreate",
    "VendorApprovedItemRead",
    "VendorCreate",
    "VendorFilter",
    "VendorRead",
    "VendorUpdate",
]
