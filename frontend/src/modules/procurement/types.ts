/**
 * Mirrors backend `app/modules/procurement/schemas/{vendors,approvals,requisitions,rfqs,
 * orders}.py` (STRUCTURE §4). Vendor masters + approved items, approval rules, and purchase
 * requisitions shipped first; this slice adds RFQs and purchase orders. Goods receipts and
 * invoice matches land in later slices of PLAN 15.6.
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
