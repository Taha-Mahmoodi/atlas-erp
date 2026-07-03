/**
 * Mirrors backend `app/modules/procurement/schemas/vendors.py` (STRUCTURE §4). Only the
 * slice the finance AP workbench needs (a vendor picker) — the full procurement module
 * lands in PLAN 15.6.
 */

export type VendorStatus = "ACTIVE" | "INACTIVE";

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
}
