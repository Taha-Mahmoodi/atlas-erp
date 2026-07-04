/**
 * Mirrors backend `app/modules/sales/schemas/masters.py` and `schemas/orders.py` (STRUCTURE
 * §4). Slice 1/4 of PLAN 15.7 (customers + pricing) is done; this file now also carries slice
 * 2/4 (quotes + sales orders). Deliveries, billing, and returns land in later slices.
 * `Customer` was already used by finance's AR workbench (a customer picker) — expanded here to
 * the full master-data shape without changing its wire fields, so those existing imports keep
 * working unchanged.
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

// --- Quotes (slice 2/4) -----------------------------------------------------------
//
// DRAFT -> SENT -> ACCEPTED -> CONVERTED (terminal, via convert-to-order) | SENT -> REJECTED
// (terminal) | CANCELLED from DRAFT/SENT/ACCEPTED (terminal) | EXPIRED (lazy: set on GET once
// past valid_until, from DRAFT/SENT). Only DRAFT is PATCH-editable; only ACCEPTED converts.

export type QuoteStatus = "DRAFT" | "SENT" | "ACCEPTED" | "REJECTED" | "CONVERTED" | "CANCELLED" | "EXPIRED";

export interface QuoteLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  uom_id: string;
  // Omit to have the service resolve it via the price resolver at line-add time (slice 1's
  // /price-quote is the same resolution, exposed standalone); supply to override.
  unit_price?: string | null;
  discount_type?: "PERCENT" | "AMOUNT" | null;
  discount_value?: string | null;
}

export interface QuoteCreate {
  customer_id: string;
  currency_code?: string | null;
  quote_date?: string | null;
  valid_until?: string | null;
  notes?: string | null;
  lines: QuoteLineCreate[];
}

// lines, when supplied, replace the whole line set wholesale (revalidated + repriced) —
// omit to leave lines untouched and only change header fields.
export type QuoteUpdate = Omit<QuoteCreate, "customer_id" | "lines"> & { lines?: QuoteLineCreate[] };

export interface QuoteLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  quantity: string;
  uom_id: string;
  unit_price: string;
  discount_type: "PERCENT" | "AMOUNT" | null;
  discount_value: string | null;
  line_amount: string;
}

export interface Quote {
  id: string;
  quote_number: string;
  customer_id: string;
  currency_code: string;
  quote_date: string;
  valid_until: string | null;
  status: QuoteStatus;
  total_amount: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuoteDetail extends Quote {
  lines: QuoteLine[];
}

export interface ConvertQuoteToOrder {
  order_date?: string | null;
  requested_date?: string | null;
  notes?: string | null;
}

// --- Sales orders (slice 2/4) ------------------------------------------------------
//
// DRAFT -> (confirm) -> CONFIRMED | CREDIT_BLOCKED -> (credit-release, then re-confirm) ->
// CONFIRMED -> PARTIALLY_DELIVERED -> DELIVERED -> INVOICED -> CLOSED (later slices).
// CANCELLED only from DRAFT. Created either standalone (POST /orders) or by converting an
// ACCEPTED quote (POST /quotes/{id}/convert-to-order) — same writer either way; conversion
// copies the quote's lines/prices/discounts/currency/customer FROZEN, never re-resolved.

export type SalesOrderStatus =
  | "DRAFT"
  | "CONFIRMED"
  | "CREDIT_BLOCKED"
  | "PARTIALLY_DELIVERED"
  | "DELIVERED"
  | "INVOICED"
  | "CLOSED"
  | "CANCELLED";

export type CreditCheckStatus = "PASSED" | "BLOCKED" | "RELEASED";

export interface SalesOrderLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  uom_id: string;
  unit_price?: string | null;
  discount_type?: "PERCENT" | "AMOUNT" | null;
  discount_value?: string | null;
  tax_code_id?: string | null;
}

export interface SalesOrderCreate {
  customer_id: string;
  currency_code?: string | null;
  order_date?: string | null;
  requested_date?: string | null;
  notes?: string | null;
  lines: SalesOrderLineCreate[];
}

// lines, when supplied, replace the whole line set wholesale (revalidated + repriced) —
// omit to leave lines untouched and only change header fields.
export type SalesOrderUpdate = Omit<SalesOrderCreate, "customer_id" | "lines"> & { lines?: SalesOrderLineCreate[] };

export interface SalesOrderLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  ordered_quantity: string;
  // Server-only, raised by later slices (mirrors procurement PO's received_quantity). DB CHECK
  // invariants: delivered_quantity <= ordered_quantity; invoiced_quantity <= delivered_quantity;
  // returned_quantity <= invoiced_quantity.
  delivered_quantity: string;
  invoiced_quantity: string;
  returned_quantity: string;
  uom_id: string;
  unit_price: string;
  discount_type: "PERCENT" | "AMOUNT" | null;
  discount_value: string | null;
  tax_code_id: string | null;
  line_amount: string;
}

export interface SalesOrder {
  id: string;
  order_number: string;
  customer_id: string;
  currency_code: string;
  order_date: string;
  requested_date: string | null;
  status: SalesOrderStatus;
  total_amount: string;
  // Snapshot from the customer at creation — never client-settable.
  payment_terms_days: number;
  source_quote_id: string | null;
  credit_check_status: CreditCheckStatus | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SalesOrderDetail extends SalesOrder {
  lines: SalesOrderLine[];
}

// --- ATP (available-to-promise) preview — read-only, never blocks confirmation ------
//
// available = on_hand - committed + on_order. committed sums (ordered - delivered) over OTHER
// CONFIRMED/PARTIALLY_DELIVERED order lines for that item; on_order comes from procurement's
// open incoming quantity. A shortfall never blocks /confirm — it only flags backordered=true
// on that line in the response; the hard gate at confirm time is the credit check, not ATP.

export interface AtpCheckLine {
  item_id: string;
  quantity: string;
}

export interface AtpCheckRequest {
  on_date?: string | null;
  lines: AtpCheckLine[];
}

export interface AtpLineResult {
  item_id: string;
  requested_quantity: string;
  on_hand: string;
  committed: string;
  on_order: string;
  available: string;
  atp_ok: boolean;
  backordered: boolean;
  shortfall: string;
}

export interface AtpCheckResponse {
  on_date: string;
  lines: AtpLineResult[];
}
