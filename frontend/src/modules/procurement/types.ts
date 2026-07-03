/**
 * Mirrors backend `app/modules/procurement/schemas/{vendors,approvals,requisitions}.py`
 * (STRUCTURE §4). Vendor masters + approved items and approval rules shipped first; this
 * slice adds purchase requisitions. RFQs, POs, goods receipts, and invoice matches land in
 * later slices of PLAN 15.6.
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
