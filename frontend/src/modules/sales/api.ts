/**
 * Typed endpoint calls for the sales module (STRUCTURE §4): customers, customer groups,
 * price lists + their line items, and the price-quote resolution lookup. Slice 1 of PLAN 15.7.
 * None of these are financial/stock-moving documents (D-013) — no idempotency keys, matching
 * the backend's actual routers (only quote/order/delivery/billing/return use Idempotent).
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  Customer,
  CustomerCreate,
  CustomerGroup,
  CustomerGroupCreate,
  CustomerGroupUpdate,
  CustomerStatus,
  CustomerUpdate,
  PriceList,
  PriceListCreate,
  PriceListItem,
  PriceListItemCreate,
  PriceListStatus,
  PriceListUpdate,
  PriceQuote,
} from "@/modules/sales/types";

export interface CustomerFilters {
  cursor?: string;
  limit?: number;
  status?: CustomerStatus;
}

export function listCustomers(filters: CustomerFilters = {}): Promise<Page<Customer>> {
  return api.get<Page<Customer>>("/sales/customers", { params: { ...filters } });
}

export function getCustomer(customerId: string): Promise<Customer> {
  return api.get<Customer>(`/sales/customers/${customerId}`);
}

export function createCustomer(payload: CustomerCreate): Promise<Customer> {
  return api.post<Customer>("/sales/customers", payload);
}

export function updateCustomer(customerId: string, payload: CustomerUpdate): Promise<Customer> {
  return api.patch<Customer>(`/sales/customers/${customerId}`, payload);
}

// --- Customer groups -------------------------------------------------------------

export interface CustomerGroupFilters {
  cursor?: string;
  limit?: number;
}

export function listCustomerGroups(filters: CustomerGroupFilters = {}): Promise<Page<CustomerGroup>> {
  return api.get<Page<CustomerGroup>>("/sales/customer-groups", { params: { ...filters } });
}

export function getCustomerGroup(customerGroupId: string): Promise<CustomerGroup> {
  return api.get<CustomerGroup>(`/sales/customer-groups/${customerGroupId}`);
}

export function createCustomerGroup(payload: CustomerGroupCreate): Promise<CustomerGroup> {
  return api.post<CustomerGroup>("/sales/customer-groups", payload);
}

export function updateCustomerGroup(
  customerGroupId: string,
  payload: CustomerGroupUpdate,
): Promise<CustomerGroup> {
  return api.patch<CustomerGroup>(`/sales/customer-groups/${customerGroupId}`, payload);
}

// --- Price lists ------------------------------------------------------------------

export interface PriceListFilters {
  cursor?: string;
  limit?: number;
  status?: PriceListStatus;
}

export function listPriceLists(filters: PriceListFilters = {}): Promise<Page<PriceList>> {
  return api.get<Page<PriceList>>("/sales/price-lists", { params: { ...filters } });
}

export function getPriceList(priceListId: string): Promise<PriceList> {
  return api.get<PriceList>(`/sales/price-lists/${priceListId}`);
}

export function createPriceList(payload: PriceListCreate): Promise<PriceList> {
  return api.post<PriceList>("/sales/price-lists", payload);
}

export function updatePriceList(priceListId: string, payload: PriceListUpdate): Promise<PriceList> {
  return api.patch<PriceList>(`/sales/price-lists/${priceListId}`, payload);
}

export function listPriceListItems(priceListId: string): Promise<PriceListItem[]> {
  return api.get<PriceListItem[]>(`/sales/price-lists/${priceListId}/items`);
}

export function createPriceListItem(
  priceListId: string,
  payload: PriceListItemCreate,
): Promise<PriceListItem> {
  return api.post<PriceListItem>(`/sales/price-lists/${priceListId}/items`, payload);
}

export function deletePriceListItem(priceListId: string, itemId: string): Promise<void> {
  return api.delete<void>(`/sales/price-lists/${priceListId}/items/${itemId}`);
}

export interface PriceQuoteParams {
  item_id: string;
  customer_id: string;
  quantity: string;
  date?: string;
}

export function getPriceQuote(params: PriceQuoteParams): Promise<PriceQuote> {
  return api.get<PriceQuote>("/sales/price-quote", { params: { ...params } });
}
