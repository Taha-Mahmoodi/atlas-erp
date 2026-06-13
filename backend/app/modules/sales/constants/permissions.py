"""Sales permission keys (D-009), registered into the core RBAC catalog at import.

Split out of the single ``constants.py`` at the 400-line cap (PLAN 7.4). One key per guarded
endpoint action; closely-related master config (customer groups) rides the parent manage key.
"""

from app.core.rbac import register_permissions

# --- Permissions (D-009): one key per guarded endpoint action -----------------
# Customer master (PLAN 7.1): read the customer master (+ customer groups) vs create/edit it.
# Customer-group management rides CUSTOMER_MANAGE (the inventory item/uom-conversion precedent:
# closely-related master config shares the parent entity's manage key — a group is a customer
# grouping, managed by whoever manages customers).
SALES_CUSTOMER_READ = "sales.customer.read"
SALES_CUSTOMER_MANAGE = "sales.customer.manage"
# Price lists (PLAN 7.1): read the price lists (+ their items, + a resolved price quote) vs
# create/edit them (and their items). Pricing is a distinct authority from the customer master.
SALES_PRICELIST_READ = "sales.pricelist.read"
SALES_PRICELIST_MANAGE = "sales.pricelist.manage"

# Quotes (PLAN 7.2): read the quote register vs create/edit/send/accept/reject/convert. A quote
# carries no committing gate (sending/accepting a quote moves no money or stock), so MANAGE covers
# every quote action — the RFQ-manage precedent (sourcing is not a committing action).
SALES_QUOTE_READ = "sales.quote.read"
SALES_QUOTE_MANAGE = "sales.quote.manage"
# Sales orders (PLAN 7.2): read vs create/edit/convert/cancel vs the privileged CONFIRM action vs
# the privileged CREDIT_RELEASE action.
#   - CONFIRM is its own key (the journal.post / po.approve precedent): confirming runs the ATP
#     evaluation + the credit-limit gate, a distinct authority from drafting an order.
#   - CREDIT_RELEASE is its own key (an approval-like override): releasing a CREDIT_BLOCKED order
#     past the limit is a manager's call, recorded in the audit trail. A clerk who can confirm
#     cannot silently override a credit block.
SALES_ORDER_READ = "sales.order.read"
SALES_ORDER_MANAGE = "sales.order.manage"
SALES_ORDER_CONFIRM = "sales.order.confirm"
SALES_ORDER_CREDIT_RELEASE = "sales.order.credit_release"

# Deliveries (PLAN 7.3): read the delivery register vs create/edit/cancel the DRAFT vs the
# privileged POST action (issue stock + post the COGS journal). POST is its own key (the
# journal.post / goods_receipt.post precedent): building a delivery note and shipping it — which
# moves stock and posts COGS — are separate authorities. A clerk who picks a delivery cannot
# silently post the goods issue.
SALES_DELIVERY_READ = "sales.delivery.read"
SALES_DELIVERY_MANAGE = "sales.delivery.manage"
SALES_DELIVERY_POST = "sales.delivery.post"

# Billing (PLAN 7.4): read the billing register vs create/edit/cancel the DRAFT vs the privileged
# POST action (trigger the AR customer invoice — recognize revenue + AR). POST is its own key (the
# journal.post / delivery.post precedent): building a billing and invoicing it are separate
# authorities. A clerk who drafts a billing cannot silently recognize revenue.
SALES_BILLING_READ = "sales.billing.read"
SALES_BILLING_MANAGE = "sales.billing.manage"
SALES_BILLING_POST = "sales.billing.post"

# Returns / RMA (PLAN 7.4): read the return register vs create/edit/cancel the DRAFT vs the
# privileged POST action (receive stock reversing COGS + post the credit note reversing revenue).
# POST is its own key (the same precedent): drafting an RMA and committing its stock + credit
# postings are separate authorities.
SALES_RETURN_READ = "sales.return.read"
SALES_RETURN_MANAGE = "sales.return.manage"
SALES_RETURN_POST = "sales.return.post"

register_permissions(
    SALES_CUSTOMER_READ,
    SALES_CUSTOMER_MANAGE,
    SALES_PRICELIST_READ,
    SALES_PRICELIST_MANAGE,
    SALES_QUOTE_READ,
    SALES_QUOTE_MANAGE,
    SALES_ORDER_READ,
    SALES_ORDER_MANAGE,
    SALES_ORDER_CONFIRM,
    SALES_ORDER_CREDIT_RELEASE,
    SALES_DELIVERY_READ,
    SALES_DELIVERY_MANAGE,
    SALES_DELIVERY_POST,
    SALES_BILLING_READ,
    SALES_BILLING_MANAGE,
    SALES_BILLING_POST,
    SALES_RETURN_READ,
    SALES_RETURN_MANAGE,
    SALES_RETURN_POST,
    descriptions={
        SALES_CUSTOMER_READ: "Read customers and customer groups",
        SALES_CUSTOMER_MANAGE: "Create and edit customers and customer groups",
        SALES_PRICELIST_READ: "Read price lists, their items and resolved price quotes",
        SALES_PRICELIST_MANAGE: "Create and edit price lists and their items",
        SALES_QUOTE_READ: "Read sales quotations",
        SALES_QUOTE_MANAGE: "Create, edit, send, accept, reject and convert sales quotations",
        SALES_ORDER_READ: "Read sales orders",
        SALES_ORDER_MANAGE: "Create, edit, convert and cancel sales orders",
        SALES_ORDER_CONFIRM: "Confirm sales orders (run the ATP and credit-limit checks)",
        SALES_ORDER_CREDIT_RELEASE: "Release a credit-blocked sales order past the credit limit",
        SALES_DELIVERY_READ: "Read outbound deliveries",
        SALES_DELIVERY_MANAGE: "Create, edit and cancel draft deliveries",
        SALES_DELIVERY_POST: "Post deliveries (issue stock and post the COGS journal)",
        SALES_BILLING_READ: "Read sales billings",
        SALES_BILLING_MANAGE: "Create, edit and cancel draft billings",
        SALES_BILLING_POST: "Post billings (trigger the AR customer invoice — revenue and AR)",
        SALES_RETURN_READ: "Read sales returns (RMA)",
        SALES_RETURN_MANAGE: "Create, edit and cancel draft returns",
        SALES_RETURN_POST: "Post returns (receive stock reversing COGS and post the credit note)",
    },
)
