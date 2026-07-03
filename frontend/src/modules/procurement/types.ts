/**
 * Mirrors backend `app/modules/procurement/schemas/{vendors,approvals}.py` (STRUCTURE §4).
 * This slice covers vendor masters (+ approved items) and approval rules; requisitions, RFQs,
 * POs, goods receipts, and invoice matches land in later slices of PLAN 15.6.
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
