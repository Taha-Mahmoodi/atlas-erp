"""Procurement service package (STRUCTURE §3: split per aggregate, each <400 lines — the single
service.py reached the cap when PLAN 6.2's requisition/RFQ/PO/approval/conversion logic landed, the
finance/inventory precedent).

The router and test factories import service functions from this package surface (``from
app.modules.procurement import service`` then ``service.create_purchase_order(...)``), so the split
is
an internal detail. Re-exported here so call sites use one import.

- ``vendors``: vendor master CRUD + approved-item management (6.1).
- ``requisitions``: requisition create/submit/approve/cancel + reads (6.2).
- ``rfqs``: RFQ create/send/record-quote/close + reads (6.2).
- ``orders``: PO create/send/approve/cancel + reads + the shared PO writer (6.2).
- ``conversions``: requisition→RFQ, requisition→PO, RFQ→PO (6.2).
- ``approvals``: approval-rule CRUD + the requires_approval value-threshold evaluator (6.2, D-040).
"""

from app.modules.procurement.service.approvals import (
    create_approval_rule,
    get_approval_rule,
    list_approval_rules,
    requires_approval,
    update_approval_rule,
)
from app.modules.procurement.service.conversions import (
    convert_requisition_to_po,
    convert_requisition_to_rfq,
    convert_rfq_to_po,
)
from app.modules.procurement.service.orders import (
    cancel_purchase_order,
    create_purchase_order,
    decide_purchase_order,
    get_purchase_order,
    get_purchase_order_lines,
    list_purchase_orders,
    send_purchase_order,
)
from app.modules.procurement.service.requisitions import (
    cancel_requisition,
    create_requisition,
    decide_requisition,
    get_requisition,
    get_requisition_lines,
    list_requisitions,
    submit_requisition,
    update_requisition,
)
from app.modules.procurement.service.rfqs import (
    close_rfq,
    create_rfq,
    get_rfq,
    get_rfq_lines,
    list_rfqs,
    record_quote,
    send_rfq,
)
from app.modules.procurement.service.vendors import (
    add_approved_item,
    create_vendor,
    get_vendor,
    list_approved_items,
    list_vendors,
    remove_approved_item,
    update_vendor,
)

__all__ = [
    "add_approved_item",
    "cancel_purchase_order",
    "cancel_requisition",
    "close_rfq",
    "convert_requisition_to_po",
    "convert_requisition_to_rfq",
    "convert_rfq_to_po",
    "create_approval_rule",
    "create_purchase_order",
    "create_requisition",
    "create_rfq",
    "create_vendor",
    "decide_purchase_order",
    "decide_requisition",
    "get_approval_rule",
    "get_purchase_order",
    "get_purchase_order_lines",
    "get_requisition",
    "get_requisition_lines",
    "get_rfq",
    "get_rfq_lines",
    "get_vendor",
    "list_approval_rules",
    "list_approved_items",
    "list_purchase_orders",
    "list_requisitions",
    "list_rfqs",
    "list_vendors",
    "record_quote",
    "remove_approved_item",
    "requires_approval",
    "send_purchase_order",
    "send_rfq",
    "submit_requisition",
    "update_approval_rule",
    "update_requisition",
    "update_vendor",
]
