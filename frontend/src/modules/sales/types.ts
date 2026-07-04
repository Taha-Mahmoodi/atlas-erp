/**
 * Mirrors backend `app/modules/sales/schemas/masters.py` (STRUCTURE §4). This is slice 1/4 of
 * PLAN 15.7: customers + pricing. Quotes, orders, deliveries, billing, and returns land in
 * later slices. `Customer` was already used by finance's AR workbench (a customer picker) —
 * expanded here to the full master-data shape without changing its wire fields, so those
 * existing imports keep working unchanged.
 */

export type CustomerStatus = "ACTIVE" | "BLOCKED" | "INACTIVE";

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
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerCreate {
  customer_code: string;
  name: string;
  default_currency_code: string;
  status?: CustomerStatus;
  customer_group_id?: string | null;
  payment_terms_days?: number;
  credit_limit?: string;
  tax_reference?: string | null;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
}

export type CustomerUpdate = Omit<CustomerCreate, "customer_code">;

export interface CustomerGroup {
  id: string;
  code: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerGroupCreate {
  code: string;
  name: string;
}

export interface CustomerGroupUpdate {
  name: string;
}

// --- Pricing (condition-style: header attribute match + one flat price per item, NOT SAP's
// access-sequence/pricing-procedure engine) -----------------------------------------------

export type PriceListStatus = "ACTIVE" | "INACTIVE";

export interface PriceList {
  id: string;
  code: string;
  name: string;
  currency_code: string;
  customer_group_id: string | null;
  valid_from: string;
  valid_to: string | null;
  status: PriceListStatus;
  priority: number;
  created_at: string;
  updated_at: string;
}

export interface PriceListCreate {
  code: string;
  name: string;
  currency_code: string;
  customer_group_id?: string | null;
  valid_from: string;
  valid_to?: string | null;
  status?: PriceListStatus;
  priority?: number;
}

export type PriceListUpdate = Omit<PriceListCreate, "code">;

export interface PriceListItem {
  id: string;
  price_list_id: string;
  item_id: string;
  unit_price: string;
  min_quantity: string;
}

export interface PriceListItemCreate {
  item_id: string;
  unit_price: string;
  min_quantity?: string;
}

// A pure read/simulation surface (GET /price-quote) — resolves what a customer would actually
// pay for an item+quantity+date, without creating any document. matched=false means no price
// list covers this combination and every price field is null.
export interface PriceQuote {
  matched: boolean;
  item_id: string;
  customer_id: string;
  quote_date: string;
  quantity: string;
  currency_code: string | null;
  unit_price: string | null;
  price_list_id: string | null;
  price_list_code: string | null;
}
