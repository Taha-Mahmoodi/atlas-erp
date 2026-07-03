/**
 * Mirrors backend `app/modules/procurement/schemas/{vendors,approvals,requisitions,rfqs,
 * orders,goods_receipts,invoice_matches}.py` (STRUCTURE §4). This is the final slice of PLAN
 * 15.6: vendor masters + approved items, approval rules, requisitions, RFQs, purchase orders,
 * and goods receipts shipped first; this slice adds the 3-way invoice match.
 */

export type VendorStatus = "ACTIVE" | "BLOCKED" | "INACTIVE";

export interface VendorCreate {
  vendor_code: string;
  name: string;
  default_currency_code: string;
  status?: VendorStatus;
  payment_terms_days?: number;
  tax_reference?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
}

export type VendorUpdate = Partial<Omit<VendorCreate, "vendor_code">>;

export interface Vendor {
  id: string;
  vendor_code: string;
  name: string;
  status: VendorStatus;
  default_currency_code: string;
  payment_terms_days: number;
  tax_reference: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface VendorApprovedItemCreate {
  item_id: string;
  vendor_item_code?: string | null;
  is_active?: boolean;
}

export interface VendorApprovedItem {
  id: string;
  vendor_id: string;
  item_id: string;
  vendor_item_code: string | null;
  is_active: boolean;
  created_at: string;
}

// --- Approval rules (mirrors schemas/approvals.py) --------------------------
//
// Value-threshold gate shared by requisitions and POs: at submit/send time, if an ACTIVE rule
// exists for that document_type AND its currency_code matches the document's, and the
// document's total >= threshold_amount, the document needs a separate decision step instead
// of auto-advancing. No matching rule (missing, inactive, or currency mismatch) means no gate
// at all — auto-approves silently, not an error.

export type ApprovalDocumentType = "REQUISITION" | "PURCHASE_ORDER";

export interface ApprovalRuleCreate {
  document_type: ApprovalDocumentType;
  threshold_amount: string;
  currency_code: string;
  is_active?: boolean;
  description?: string | null;
}

export type ApprovalRuleUpdate = Partial<Omit<ApprovalRuleCreate, "document_type">>;

export interface ApprovalRule {
  id: string;
  document_type: ApprovalDocumentType;
  threshold_amount: string;
  currency_code: string;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalDecisionPayload {
  decision: "APPROVED" | "REJECTED";
  comment?: string | null;
}

// --- Purchase requisitions (mirrors schemas/requisitions.py) ----------------
//
// DRAFT -> SUBMITTED (if a REQUISITION approval rule applies to the total) -> APPROVED |
// REJECTED, or DRAFT -> APPROVED directly when no rule applies (auto-approve, no separate
// decision step). APPROVED -> CONVERTED once turned into an RFQ or PO. CANCELLED from DRAFT
// or APPROVED. Only DRAFT can be edited (PATCH replaces the whole line set wholesale).

export type RequisitionStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "APPROVED"
  | "REJECTED"
  | "CONVERTED"
  | "CANCELLED";

export interface RequisitionLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  uom_id: string;
  estimated_unit_cost?: string | null;
  currency_code: string;
}

export interface RequisitionCreate {
  requested_by?: string | null;
  needed_by_date?: string | null;
  notes?: string | null;
  lines: RequisitionLineCreate[];
}

export interface RequisitionUpdate {
  requested_by?: string | null;
  needed_by_date?: string | null;
  notes?: string | null;
  lines?: RequisitionLineCreate[] | null;
}

export interface RequisitionLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  quantity: string;
  uom_id: string;
  estimated_unit_cost: string | null;
  currency_code: string;
}

export interface Requisition {
  id: string;
  requisition_number: string;
  status: RequisitionStatus;
  requested_by: string | null;
  needed_by_date: string | null;
  notes: string | null;
  document_id: string;
  created_at: string;
  updated_at: string;
}

export interface RequisitionDetail extends Requisition {
  lines: RequisitionLine[];
}

export interface RfqFromRequisition {
  vendor_id: string;
  currency_code?: string | null;
  valid_until?: string | null;
  notes?: string | null;
}

export interface PurchaseOrderFromRequisition {
  vendor_id: string;
  order_date?: string | null;
  expected_date?: string | null;
  notes?: string | null;
}

// --- RFQs (mirrors schemas/rfqs.py) ------------------------------------------
//
// DRAFT -> SENT -> QUOTED -> CLOSED, or CANCELLED from any non-terminal state. No approval
// gate on RFQs — sourcing quotes isn't a financial commitment, only the resulting PO is.
// Lines carry no price at creation; record-quote fills in quoted_unit_cost per line and
// advances SENT -> QUOTED.

export type RfqStatus = "DRAFT" | "SENT" | "QUOTED" | "CLOSED" | "CANCELLED";

export interface RfqLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  uom_id: string;
}

export interface RfqCreate {
  vendor_id: string;
  currency_code: string;
  valid_until?: string | null;
  notes?: string | null;
  lines: RfqLineCreate[];
}

export interface RfqLineQuote {
  line_id: string;
  quoted_unit_cost: string;
}

export interface RecordQuotePayload {
  quotes: RfqLineQuote[];
}

export interface RfqLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  quantity: string;
  uom_id: string;
  quoted_unit_cost: string | null;
}

export interface Rfq {
  id: string;
  rfq_number: string;
  status: RfqStatus;
  vendor_id: string;
  currency_code: string;
  valid_until: string | null;
  source_requisition_id: string | null;
  notes: string | null;
  document_id: string;
  created_at: string;
  updated_at: string;
}

export interface RfqDetail extends Rfq {
  lines: RfqLine[];
}

export interface PurchaseOrderFromRfq {
  order_date?: string | null;
  expected_date?: string | null;
  notes?: string | null;
}

// --- Purchase orders (mirrors schemas/orders.py) -----------------------------
//
// DRAFT -> (send) -> PENDING_APPROVAL (if a PURCHASE_ORDER approval rule applies) -> APPROVED
// | REJECTED -> SENT, or DRAFT -> SENT directly when no rule applies. SENT -> (GR posts) ->
// PARTIALLY_RECEIVED -> RECEIVED -> (match posts, fully received+billed) -> CLOSED.
// REJECTED/CANCELLED are terminal side-branches. received_quantity is server-maintained
// (raised by goods-receipt posting, not editable here); billed_quantity exists on the backend
// model but isn't exposed on the line read schema.

export type PurchaseOrderStatus =
  | "DRAFT"
  | "PENDING_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "SENT"
  | "PARTIALLY_RECEIVED"
  | "RECEIVED"
  | "CLOSED"
  | "CANCELLED";

export interface PurchaseOrderLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  uom_id: string;
  unit_cost: string;
  tax_code_id?: string | null;
}

export interface PurchaseOrderCreate {
  vendor_id: string;
  currency_code?: string | null;
  order_date?: string | null;
  expected_date?: string | null;
  notes?: string | null;
  lines: PurchaseOrderLineCreate[];
}

export interface PurchaseOrderLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  quantity: string;
  uom_id: string;
  unit_cost: string;
  line_amount: string;
  received_quantity: string;
  tax_code_id: string | null;
}

export interface PurchaseOrder {
  id: string;
  po_number: string;
  status: PurchaseOrderStatus;
  vendor_id: string;
  currency_code: string;
  order_date: string;
  expected_date: string | null;
  payment_terms_days: number;
  total_amount: string;
  notes: string | null;
  approved_by: string | null;
  approved_at: string | null;
  source_requisition_id: string | null;
  source_rfq_id: string | null;
  document_id: string;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderDetail extends PurchaseOrder {
  lines: PurchaseOrderLine[];
}

// --- Goods receipts (mirrors schemas/goods_receipts.py) ----------------------
//
// DRAFT -> POSTED (terminal, no un-post) or CANCELLED (DRAFT only). Posting publishes
// GoodsReceiptPosted: inventory creates the stock RECEIPT moves and finance posts the GR/IR
// journal, all in the same transaction as the post call — there's no separate "create stock
// move" step for the frontend to call. item_id/unit_cost are snapshotted server-side from the
// referenced PO line and are NOT client-settable on the create payload.

export type GoodsReceiptStatus = "DRAFT" | "POSTED" | "CANCELLED";

export interface GoodsReceiptLineCreate {
  purchase_order_line_id: string;
  bin_id: string;
  received_quantity: string;
  lot_code?: string | null;
  serial_code?: string | null;
  requires_inspection?: boolean | null;
}

export interface GoodsReceiptCreate {
  purchase_order_id: string;
  warehouse_id: string;
  receipt_date?: string | null;
  notes?: string | null;
  lines: GoodsReceiptLineCreate[];
}

export interface GoodsReceiptLine {
  id: string;
  line_number: number;
  purchase_order_line_id: string;
  item_id: string;
  bin_id: string;
  received_quantity: string;
  unit_cost: string;
  lot_code: string | null;
  serial_code: string | null;
  requires_inspection: boolean;
}

export interface GoodsReceipt {
  id: string;
  gr_number: string;
  status: GoodsReceiptStatus;
  purchase_order_id: string;
  vendor_id: string;
  warehouse_id: string;
  receipt_date: string;
  notes: string | null;
  posted_at: string | null;
  document_id: string;
  created_at: string;
  updated_at: string;
}

export interface GoodsReceiptDetail extends GoodsReceipt {
  lines: GoodsReceiptLine[];
}

// --- Invoice matches (mirrors schemas/invoice_matches.py) --------------------
//
// DRAFT -> MATCHED | EXCEPTION (computed at create time from each line's price/quantity
// variance vs MatchTolerance) -> POSTED (terminal; blocked from EXCEPTION, use /override
// first) or CANCELLED. Posting publishes InvoiceMatched: finance creates+posts the AP vendor
// bill in the same transaction — there is NO "create bill" endpoint here; the resulting bill
// is only visible via finance's own VendorBillListPage/VendorBillDetailPage (D-042: no
// vendor_bill_id FK on this schema by design). po_unit_cost/price_variance/quantity_variance/
// within_tolerance are server-computed, never client-settable.
//
// Quantity variance is NOT simply matched-vs-received: if goods_receipt_line_id is given,
// expected quantity is THAT receipt line's received_quantity; otherwise it's the PO line's
// open-to-bill quantity (received - billed). variance = max(0, matched - expected) — billing
// LESS than expected (an ordinary partial invoice) is never a variance (issue #74's fix).
//
// price_variance is a MONEY AMOUNT — (unit_price - po_unit_cost) * matched_quantity — not a
// percentage; render with formatMoney, not a raw "%" suffix (a real bug this slice's own QA
// caught: a $10->$15 price on 100 units rendered as "500%" instead of "USD 500.00"). The
// tolerance *percentage* used for within_tolerance is computed server-side but not itself
// exposed on the line.

export type MatchStatus = "DRAFT" | "MATCHED" | "EXCEPTION" | "POSTED" | "CANCELLED";

export interface InvoiceMatchLineCreate {
  purchase_order_line_id: string;
  goods_receipt_line_id?: string | null;
  matched_quantity: string;
  unit_price: string;
}

export interface InvoiceMatchCreate {
  purchase_order_id: string;
  vendor_invoice_ref?: string | null;
  invoice_date?: string | null;
  tax_code_id?: string | null;
  notes?: string | null;
  lines: InvoiceMatchLineCreate[];
}

export interface InvoiceMatchLine {
  id: string;
  line_number: number;
  purchase_order_line_id: string;
  goods_receipt_line_id: string | null;
  item_id: string;
  matched_quantity: string;
  unit_price: string;
  po_unit_cost: string;
  price_variance: string;
  quantity_variance: string;
  line_amount: string;
  within_tolerance: boolean;
}

export interface InvoiceMatch {
  id: string;
  match_number: string;
  status: MatchStatus;
  purchase_order_id: string;
  vendor_id: string;
  vendor_invoice_ref: string | null;
  invoice_date: string;
  currency_code: string;
  total_amount: string;
  tax_code_id: string | null;
  notes: string | null;
  document_id: string;
  posted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvoiceMatchDetail extends InvoiceMatch {
  lines: InvoiceMatchLine[];
}

export interface MatchToleranceUpsert {
  price_tolerance_percent?: string;
  quantity_tolerance_percent?: string;
}

export interface MatchTolerance {
  id: string;
  price_tolerance_percent: string;
  quantity_tolerance_percent: string;
  created_at: string;
  updated_at: string;
}
