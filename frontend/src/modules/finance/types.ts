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
