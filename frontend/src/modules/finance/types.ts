/**
 * Mirrors backend `app/modules/finance/schemas.py` + `constants/enums.py` (STRUCTURE §4).
 * snake_case kept as-is. Money/quantity fields are decimal STRINGS on the wire (D-015) —
 * never parsed to float except at the lib/format.ts display boundary.
 */

export type AccountType = "ASSET" | "LIABILITY" | "EQUITY" | "REVENUE" | "EXPENSE";

export interface Currency {
  id: string;
  code: string;
  name: string;
  decimal_places: number;
  is_functional: boolean;
}
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

/** Shared by AP and AR — the backend's AgingBucketRead / ArAgingBucketRead are structurally
 * identical (partner-vs-partner buckets), just named per module. */
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

// --- Accounts Receivable (mirrors backend receivables_schemas.py) --------------

export type InvoiceStatus = "DRAFT" | "POSTED" | "PARTIALLY_PAID" | "PAID" | "REVERSED";
export type ReceiptStatus = "DRAFT" | "POSTED" | "REVERSED";

export interface CustomerInvoiceLineCreate {
  account_id: string;
  description?: string | null;
  net_amount: string;
  tax_code_id?: string | null;
}

export interface CustomerInvoiceCreate {
  partner_id: string;
  partner_name: string;
  invoice_date: string;
  due_date: string;
  currency_code: string;
  ar_account_id: string;
  external_ref?: string | null;
  description?: string | null;
  lines: CustomerInvoiceLineCreate[];
}

export interface CustomerInvoiceLine {
  id: string;
  line_number: number;
  account_id: string;
  description: string | null;
  net_amount: string;
  tax_code_id: string | null;
  tax_amount: string;
  cost_center_id: string | null;
  profit_center_id: string | null;
  project_id: string | null;
}

export interface CustomerInvoice {
  id: string;
  partner_id: string;
  partner_name: string;
  external_ref: string | null;
  invoice_number: string | null;
  invoice_date: string;
  due_date: string;
  currency_code: string;
  status: InvoiceStatus;
  ar_account_id: string;
  journal_entry_id: string | null;
  gross_amount: string;
  tax_amount: string;
  net_amount: string;
  open_amount: string;
  dunning_level: number;
  last_dunned_date: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerInvoiceDetail extends CustomerInvoice {
  lines: CustomerInvoiceLine[];
}

export interface ReceiptAllocationCreate {
  invoice_id: string;
  amount: string;
}

export interface CustomerReceiptCreate {
  partner_id: string;
  partner_name: string;
  receipt_date: string;
  currency_code: string;
  bank_account_id: string;
  amount: string;
  description?: string | null;
  allocations: ReceiptAllocationCreate[];
}

export interface ReceiptAllocation {
  id: string;
  receipt_id: string;
  customer_invoice_id: string;
  allocated_amount: string;
}

export interface CustomerReceipt {
  id: string;
  partner_id: string;
  partner_name: string;
  receipt_number: string | null;
  receipt_date: string;
  currency_code: string;
  bank_account_id: string;
  amount: string;
  journal_entry_id: string | null;
  status: ReceiptStatus;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerReceiptDetail extends CustomerReceipt {
  allocations: ReceiptAllocation[];
}

// --- Dunning ---------------------------------------------------------------

export interface DunningRunRequest {
  as_of: string;
  partner_id?: string | null;
}

export interface DunningNotice {
  partner_id: string;
  partner_name: string;
  invoice_id: string;
  invoice_number: string | null;
  currency_code: string;
  open_amount: string;
  due_date: string;
  days_overdue: number;
  previous_level: number;
  new_level: number;
}

export interface DunningRunResult {
  as_of: string;
  notices: DunningNotice[];
}

// --- Financial statements (mirrors backend statements_schemas.py) ----------
//
// All money fields are Decimal on the wire (D-015) — typed `string` here, formatted only via
// lib/format.ts. Every statement below has already been re-signed to natural presentation
// magnitude server-side (revenue/liabilities/equity/expenses/assets all show positive) — no
// sign-flipping needed client-side. Trial balance and balance sheet are cumulative-to-date
// (as_of only); P&L and cash flow are period-bound (date_from/date_to).

export interface TrialBalanceRow {
  account_id: string;
  account_code: string;
  account_name: string;
  account_type: AccountType;
  debit: string;
  credit: string;
}

export interface TrialBalance {
  as_of: string;
  rows: TrialBalanceRow[];
  total_debit: string;
  total_credit: string;
  is_balanced: boolean;
}

export interface StatementLine {
  account_id: string;
  account_code: string;
  account_name: string;
  amount: string;
}

export interface StatementGroup {
  group_code: string;
  group_name: string;
  lines: StatementLine[];
  subtotal: string;
}

export interface ProfitAndLoss {
  date_from: string;
  date_to: string;
  revenue_groups: StatementGroup[];
  expense_groups: StatementGroup[];
  revenue_total: string;
  expense_total: string;
  net_income: string;
}

/** Balance sheet's retained-earnings synthetic line (account_id sentinel, not a real account,
 * group_code "EARNINGS") is included directly in equity_groups by the backend — no special
 * handling needed beyond not looking it up in the Chart of Accounts. */
export interface BalanceSheet {
  as_of: string;
  asset_groups: StatementGroup[];
  liability_groups: StatementGroup[];
  equity_groups: StatementGroup[];
  asset_total: string;
  liability_total: string;
  equity_total: string;
  retained_earnings: string;
  is_balanced: boolean;
}

export interface CashFlowLine {
  account_id: string;
  account_code: string;
  account_name: string;
  amount: string;
}

export interface CashFlowCategorySection {
  category: CashFlowCategory;
  lines: CashFlowLine[];
  subtotal: string;
}

export interface CashFlowStatement {
  date_from: string;
  date_to: string;
  net_income: string;
  sections: CashFlowCategorySection[];
  net_change_from_activities: string;
  cash_account_movement: string;
  is_reconciled: boolean;
}

// --- Bank reconciliation (mirrors backend bank_schemas.py) ------------------
//
// A "bank account" is just a regular Account with is_cash_equivalent = true — no separate
// model. Lines only ever come from CSV import (no manual create); matching is exclusively
// automatic suggest-matches followed by confirm/reject — there's no manual bank-line <->
// journal-line pairing action, no un-matching a MATCHED line, and no reopening a CLEARED one.

export type StatementStatus = "IMPORTED" | "PARTIALLY_RECONCILED" | "RECONCILED";
export type LineStatus = "UNMATCHED" | "SUGGESTED" | "MATCHED" | "CLEARED";

export interface BankStatementImportRequest {
  bank_account_id: string;
  statement_date: string;
  opening_balance: string;
  closing_balance: string;
  currency_code: string;
  csv_text: string;
  source_filename?: string | null;
}

export interface BankStatement {
  id: string;
  bank_account_id: string;
  statement_date: string;
  opening_balance: string;
  closing_balance: string;
  currency_code: string;
  status: StatementStatus;
  line_count: number;
  import_job_id: string | null;
  source_filename: string | null;
  created_at: string;
}

export interface StatementProgress {
  total: number;
  unmatched: number;
  suggested: number;
  matched: number;
  cleared: number;
  resolved: number;
}

export interface BankStatementDetail extends BankStatement {
  progress: StatementProgress;
}

/** amount is SIGNED: positive = money in (credit to bank), negative = money out. */
export interface BankStatementLine {
  id: string;
  statement_id: string;
  line_number: number;
  value_date: string;
  amount: string;
  description: string;
  counterparty_ref: string | null;
  status: LineStatus;
  matched_journal_line_id: string | null;
  cleared_journal_entry_id: string | null;
}

export interface SuggestMatchesResult {
  suggested: number;
  unmatched: number;
}

export interface ClearLineRequest {
  contra_account_id?: string | null;
}
