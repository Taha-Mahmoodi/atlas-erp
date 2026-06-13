"""Sales document types, number sequences, docflow link types and domain-event keys (D-012/D-040).

Split out of the single ``constants.py`` at the 400-line cap (PLAN 7.4). Each sales document
(quote, order, delivery, billing, return) registers in core_documents and claims a gapless number AT
CREATION (D-040, the procurement-document precedent — not finance's number-at-post branch). The
event keys name the in-process domain events the POST paths publish (D-011); the cross-module
handlers subscribe by these keys.
"""


# --- Document types + number sequences (D-012/D-040) --------------------------
# The two O2C documents register in core_documents and claim a gapless number AT CREATION (D-040:
# claim-at-creation so a quote/order is referenceable the moment it exists — the
# procurement-document
# precedent, not finance's number-at-post branch). Sequences year-reset (QUO-2026-00001 /
# SO-2026-00001). Gaplessness still holds because creation is the committing transaction.
QUOTE_DOC_TYPE = "sales.quote"
QUOTE_SEQUENCE_NAME = "sales.quote"
QUOTE_NUMBER_PREFIX = "QUO"
QUOTE_NUMBER_PADDING = 5

SALES_ORDER_DOC_TYPE = "sales.order"
SALES_ORDER_SEQUENCE_NAME = "sales.order"
SALES_ORDER_NUMBER_PREFIX = "SO"
SALES_ORDER_NUMBER_PADDING = 5

# docflow link type joining the chain (D-012 vocabulary). The edge is predecessor → successor, so
# the
# link_type names the edge from the predecessor's point of view: an ACCEPTED quote is "converted_to"
# the order raised from it (the order carries source_quote_id; the quote→order edge is the chain the
# DocFlowViewer renders). The reverse ("quoted_by") is the successor's view, kept here for the docs.
QUOTE_CONVERTED_TO_ORDER_LINK = "converted_to"

# Delivery (PLAN 7.3): the outbound fulfilment document. Registers in core_documents + claims a
# gapless DN number AT CREATION (D-040; year-resetting DN-2026-00001), the goods-receipt precedent.
# A delivery is built DRAFT then POSTED; the POST issues stock (an inventory ISSUE move per line)
# whose costing posts COGS — but the delivery claims its OWN DN- number, distinct from the STK- the
# inventory move claims.
DELIVERY_DOC_TYPE = "sales.delivery"
DELIVERY_SEQUENCE_NAME = "sales.delivery"
DELIVERY_NUMBER_PREFIX = "DN"
DELIVERY_NUMBER_PADDING = 5

# Delivery docflow edges (PLAN 7.3, D-041). The edge is predecessor → successor named from the
# predecessor's point of view:
#   order → delivery   : the sales order is "delivered_by" the delivery (written by sales at POST).
#   delivery → move    : the delivery is "moved_by" each inventory ISSUE move it generates (written
#                        by INVENTORY's handler when it creates the moves — the GR "moved_by"
#                        precedent; the delivery↔move linkage is docflow, NOT a cross-module FK).
ORDER_DELIVERED_BY_DELIVERY_LINK = "delivered_by"
DELIVERY_MOVED_BY_STOCK_MOVE_LINK = "moved_by"

# The sales domain event the delivery POST publishes (D-011/D-041): inventory's handlers.py
# subscribes and creates the stock ISSUE moves in the SAME transaction (the sanctioned cross-module
# mechanism — sales never imports inventory/service). Mirrors GOODS_RECEIPT_POSTED_EVENT_KEY, but
# the event carries NO GL accounts: an ISSUE move's default offset IS the item-category COGS
# account (resolved inside the costing engine), so unlike the GR/IR receipt there is no offset to
# override.
DELIVERY_SHIPPED_EVENT_KEY = "sales.delivery.shipped"


# --- Billing (PLAN 7.4, D-046) ------------------------------------------------
# The sales-side billing document. Registers in core_documents + claims a gapless BIL number AT
# CREATION (D-040; year-resetting BIL-2026-00001), the delivery precedent. A billing is built DRAFT
# then POSTED; the POST publishes the billing event so FINANCE creates + posts the AR customer
# invoice (Dr AR / Cr revenue + tax) — but the billing claims its OWN BIL- number, distinct from the
# INV- the finance customer invoice claims (D-046: two numbers, the sales doc triggers the finance
# doc, mirroring the procurement match → AP bill split).
BILLING_DOC_TYPE = "sales.billing"
BILLING_SEQUENCE_NAME = "sales.billing"
BILLING_NUMBER_PREFIX = "BIL"
BILLING_NUMBER_PADDING = 5

# Billing docflow edges (PLAN 7.4, D-046). Each edge is predecessor → successor, named from the
# predecessor's point of view:
#   order    → billing : the sales order is "billed_by" the billing (written by sales at POST).
# delivery → billing : each delivery a billing bills is "invoiced_by" the billing (written by sales
#                        at create from the lines' delivery_line_id).
#   billing  → invoice : the billing is "invoiced_by_invoice" the FINANCE customer invoice it
#                        triggers (written by FINANCE's handler when it posts the AR invoice — the
# match→bill 'billed_by' precedent; the billing↔invoice link is docflow, NOT a
#                        cross-module FK).
ORDER_BILLED_BY_BILLING_LINK = "billed_by"
DELIVERY_INVOICED_BY_BILLING_LINK = "invoiced_by"
BILLING_INVOICED_BY_INVOICE_LINK = "invoiced_by_invoice"

# The sales domain event the billing POST publishes (D-011/D-046): finance's handlers.py subscribes
# and creates + posts the AR customer invoice in the SAME transaction (the sanctioned cross-module
# mechanism — sales never imports finance/service). The MIRROR of procurement's
# INVOICE_MATCHED_EVENT
# (match → AP bill), sign-flipped to billing → AR invoice. The event carries the resolved AR control
# + sales-revenue accounts (sales reads them from finance/queries before publishing) so the handler
# is a thin builder, exactly like the AP-bill handler.
BILLING_POSTED_EVENT_KEY = "sales.billing.posted"


# --- Returns / RMA (PLAN 7.4, D-046) ------------------------------------------
# The reverse-O2C document. Registers in core_documents + claims a gapless RMA number AT CREATION
# (D-040; year-resetting RMA-2026-00001). A return is built DRAFT then POSTED; the POST publishes
# TWO
# events: one the inventory handler turns into a stock RECEIPT move (goods back, Dr Inventory / Cr
# COGS — the COGS-offset OVERRIDE reverses the issue) and one the finance handler turns into an AR
# credit note (Dr revenue / Cr AR — reversing the billing). The return claims its OWN RMA- number,
# distinct from the STK- the inventory move and the CN- the finance credit note claim.
RETURN_DOC_TYPE = "sales.return"
RETURN_SEQUENCE_NAME = "sales.return"
RETURN_NUMBER_PREFIX = "RMA"
RETURN_NUMBER_PADDING = 5

# Return docflow edges (PLAN 7.4, D-046). Each edge predecessor → successor from the predecessor's
# view:
#   order   → return      : the sales order is "returned_by" the return (written by sales at POST).
#   return  → stock-move   : the return is "received_by" each inventory RECEIPT move it generates
#                            (written by INVENTORY's handler when it creates the moves — the
#                            delivery 'moved_by' precedent; the return↔move link is docflow, NOT a
#                            cross-module FK).
# return  → credit-note  : the return is "credited_by" the FINANCE credit note it triggers (written
#                            by FINANCE's handler when it posts the credit note).
ORDER_RETURNED_BY_RETURN_LINK = "returned_by"
RETURN_RECEIVED_BY_STOCK_MOVE_LINK = "received_by"
RETURN_CREDITED_BY_CREDIT_NOTE_LINK = "credited_by"

# The TWO sales domain events the return POST publishes (D-011/D-046):
#   sales.return.received  → INVENTORY's handler creates the RECEIPT moves (goods back into the bin,
# valuation_offset_account_id = the item-category COGS account so the move
#                            posts Dr Inventory / Cr COGS — REVERSING the original issue's COGS).
# sales.return.credited  → FINANCE's handler creates + posts the AR credit note (Dr revenue / Cr AR
# + reverse output tax). Two events (not one) so each module subscribes to
#                            exactly the effect it owns — the inventory move and the finance credit
#                            are independent legs of the same atomic return post (documented in
#                            events.py).
RETURN_RECEIVED_EVENT_KEY = "sales.return.received"
RETURN_CREDITED_EVENT_KEY = "sales.return.credited"
