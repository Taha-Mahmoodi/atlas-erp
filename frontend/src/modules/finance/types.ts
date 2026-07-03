/**
 * Mirrors backend `app/modules/finance/schemas.py` + `constants/enums.py` (STRUCTURE §4).
 * snake_case kept as-is. Money/quantity fields are decimal STRINGS on the wire (D-015) —
 * never parsed to float except at the lib/format.ts display boundary.
 */

export type AccountType = "ASSET" | "LIABILITY" | "EQUITY" | "REVENUE" | "EXPENSE";
export type NormalBalance = "DEBIT" | "CREDIT";
export type CashFlowCategory = "OPERATING" | "INVESTING" | "FINANCING";
export type EntryStatus = "DRAFT" | "POSTED" | "REVERSED";
export type DocumentType =
  | "JOURNAL"
  | "AP_INVOICE"
  | "AR_INVOICE"
  | "AR_CREDIT_NOTE"
  | "PAYMENT"
  | "COGS"
  | "FX_REVAL"
  | "DEPRECIATION"
  | "PAYROLL";

export const ACCOUNT_TYPES: AccountType[] = ["ASSET", "LIABILITY", "EQUITY", "REVENUE", "EXPENSE"];

export interface Account {
  id: string;
  code: string;
  name: string;
  account_type: AccountType;
  normal_balance: NormalBalance;
  is_postable: boolean;
  cash_flow_category: CashFlowCategory | null;
  is_cash_equivalent: boolean;
  account_group_id: string | null;
  is_active: boolean;
  is_monetary: boolean;
  currency_code: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccountCreate {
  code: string;
  name: string;
  account_type: AccountType;
  normal_balance?: NormalBalance;
  is_postable?: boolean;
  cash_flow_category?: CashFlowCategory | null;
  is_cash_equivalent?: boolean;
  account_group_id?: string | null;
  is_active?: boolean;
  is_monetary?: boolean;
  currency_code?: string | null;
}

/** code and account_type are immutable after creation (backend docstring). */
export interface AccountUpdate {
  name?: string;
  normal_balance?: NormalBalance;
  is_postable?: boolean;
  cash_flow_category?: CashFlowCategory | null;
  is_cash_equivalent?: boolean;
  account_group_id?: string | null;
  is_active?: boolean;
  is_monetary?: boolean;
  currency_code?: string | null;
}

export interface AccountGroup {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface JournalLine {
  id: string;
  line_number: number;
  account_id: string;
  description: string | null;
  transaction_debit_amount: string;
  transaction_credit_amount: string;
  functional_debit_amount: string;
  functional_credit_amount: string;
  currency_code: string;
  cost_center_id: string | null;
  profit_center_id: string | null;
  project_id: string | null;
  item_id: string | null;
  partner_type: string | null;
  partner_id: string | null;
  is_posted: boolean;
  posting_date: string | null;
  fiscal_period_id: string | null;
}

export interface JournalLineCreate {
  account_id: string;
  description?: string | null;
  transaction_debit_amount: string;
  transaction_credit_amount: string;
}

export interface JournalEntryCreate {
  posting_date: string;
  currency_code: string;
  description?: string | null;
  lines: JournalLineCreate[];
}

export interface JournalEntryReverseRequest {
  reversal_date: string;
  description?: string | null;
}

export interface JournalEntry {
  id: string;
  entry_number: string | null;
  posting_date: string;
  fiscal_period_id: string | null;
  document_type: DocumentType;
  currency_code: string;
  description: string | null;
  status: EntryStatus;
  reverses_entry_id: string | null;
  reversed_by_entry_id: string | null;
  posted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JournalEntryDetail extends JournalEntry {
  lines: JournalLine[];
}

// --- Tax codes -----------------------------------------------------------------

export interface TaxCode {
  id: string;
  code: string;
  name: string;
  rate_percent: string;
  jurisdiction: string | null;
  is_inclusive: boolean;
  is_active: boolean;
  tax_payable_account_id: string | null;
  tax_receivable_account_id: string | null;
  created_at: string;
}

// --- Accounts Payable (mirrors backend payables_schemas.py) --------------------

export type BillStatus = "DRAFT" | "POSTED" | "PARTIALLY_PAID" | "PAID" | "REVERSED";
export type PaymentStatus = "DRAFT" | "POSTED" | "REVERSED";

export interface VendorBillLineCreate {
  account_id: string;
  description?: string | null;
  net_amount: string;
  tax_code_id?: string | null;
}

export interface VendorBillCreate {
  partner_id: string;
  partner_name: string;
  bill_date: string;
  due_date: string;
  currency_code: string;
  ap_account_id: string;
  bill_external_ref?: string | null;
  description?: string | null;
  lines: VendorBillLineCreate[];
}

export interface VendorBillLine {
  id: string;
  line_number: number;
  account_id: string;
  description: string | null;
  net_amount: string;
  tax_code_id: string | null;
  tax_amount: string;
  cost_center_id: string | null;
  project_id: string | null;
}

export interface VendorBill {
  id: string;
  partner_id: string;
  partner_name: string;
  bill_external_ref: string | null;
  bill_number: string | null;
  bill_date: string;
  due_date: string;
  currency_code: string;
  status: BillStatus;
  ap_account_id: string;
  journal_entry_id: string | null;
  gross_amount: string;
  tax_amount: string;
  net_amount: string;
  open_amount: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface VendorBillDetail extends VendorBill {
  lines: VendorBillLine[];
}

export interface PaymentAllocationCreate {
  bill_id: string;
  amount: string;
}

export interface VendorPaymentCreate {
  partner_id: string;
  partner_name: string;
  payment_date: string;
  currency_code: string;
  bank_account_id: string;
  amount: string;
  description?: string | null;
  allocations: PaymentAllocationCreate[];
}

export interface PaymentAllocation {
  id: string;
  payment_id: string;
  vendor_bill_id: string;
  allocated_amount: string;
}

export interface VendorPayment {
  id: string;
  partner_id: string;
  partner_name: string;
  payment_number: string | null;
  payment_date: string;
  currency_code: string;
  bank_account_id: string;
  amount: string;
  journal_entry_id: string | null;
  status: PaymentStatus;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface VendorPaymentDetail extends VendorPayment {
  allocations: PaymentAllocation[];
}

export interface AgingBucket {
  partner_id: string;
  partner_name: string;
  currency_code: string;
  current: string;
  days_1_30: string;
  days_31_60: string;
  days_61_90: string;
  days_over_90: string;
  total: string;
}

export interface AgingReport {
  as_of: string;
  partners: AgingBucket[];
  current: string;
  days_1_30: string;
  days_31_60: string;
  days_61_90: string;
  days_over_90: string;
  total: string;
}
