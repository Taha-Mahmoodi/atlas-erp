/**
 * Mirrors backend `app/modules/sales/schemas/masters.py` (STRUCTURE §4). Only the slice the
 * finance AR workbench needs (a customer picker) — the full sales module lands in PLAN 15.7.
 */

export type CustomerStatus = "ACTIVE" | "INACTIVE";

export interface Customer {
  id: string;
  customer_code: string;
  name: string;
  status: CustomerStatus;
  customer_group_id: string | null;
  default_currency_code: string;
  payment_terms_days: number;
  credit_limit: string;
  tax_reference: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
}
