/**
 * Typed endpoint calls for the sales module (STRUCTURE §4): customers, customer groups, price
 * lists + their line items, the price-quote resolution lookup (slice 1), quotes + sales orders
 * + ATP preview (slice 2), and deliveries (slice 3). Customers/groups/price-lists are plain
 * master data — no idempotency keys (D-013 applies to document-creating endpoints only, per
 * the backend's actual routers). Quote/order/delivery create+post+send+accept+reject+convert+
 * confirm+credit-release ARE idempotent; every `cancel`/`PATCH`/ATP-preview call is not.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  AtpCheckRequest,
  AtpCheckResponse,
  ConvertQuoteToOrder,
  Customer,
  CustomerCreate,
  CustomerGroup,
  CustomerGroupCreate,
  CustomerGroupUpdate,
  CustomerStatus,
  CustomerUpdate,
  Delivery,
  DeliveryCreate,
  DeliveryDetail,
  DeliveryStatus,
  PriceList,
  PriceListCreate,
  PriceListItem,
  PriceListItemCreate,
  PriceListStatus,
  PriceListUpdate,
  PriceQuote,
  Quote,
  QuoteCreate,
  QuoteDetail,
  QuoteStatus,
  QuoteUpdate,
  SalesOrder,
  SalesOrderCreate,
  SalesOrderDetail,
  SalesOrderStatus,
  SalesOrderUpdate,
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

// --- Quotes -----------------------------------------------------------------------

export interface QuoteFilters {
  cursor?: string;
  limit?: number;
  status?: QuoteStatus;
  customer_id?: string;
}

export function listQuotes(filters: QuoteFilters = {}): Promise<Page<Quote>> {
  return api.get<Page<Quote>>("/sales/quotes", { params: { ...filters } });
}

export function getQuote(quoteId: string): Promise<QuoteDetail> {
  return api.get<QuoteDetail>(`/sales/quotes/${quoteId}`);
}

export function createQuote(payload: QuoteCreate): Promise<QuoteDetail> {
  return api.post<QuoteDetail>("/sales/quotes", payload, { idempotencyKey: newIdempotencyKey() });
}

export function updateQuote(quoteId: string, payload: QuoteUpdate): Promise<QuoteDetail> {
  return api.patch<QuoteDetail>(`/sales/quotes/${quoteId}`, payload);
}

export function sendQuote(quoteId: string): Promise<QuoteDetail> {
  return api.post<QuoteDetail>(`/sales/quotes/${quoteId}/send`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function acceptQuote(quoteId: string): Promise<QuoteDetail> {
  return api.post<QuoteDetail>(`/sales/quotes/${quoteId}/accept`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function rejectQuote(quoteId: string): Promise<QuoteDetail> {
  return api.post<QuoteDetail>(`/sales/quotes/${quoteId}/reject`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelQuote(quoteId: string): Promise<QuoteDetail> {
  return api.post<QuoteDetail>(`/sales/quotes/${quoteId}/cancel`, undefined);
}

export function convertQuoteToOrder(quoteId: string, payload: ConvertQuoteToOrder): Promise<SalesOrderDetail> {
  return api.post<SalesOrderDetail>(`/sales/quotes/${quoteId}/convert-to-order`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

// --- Sales orders -------------------------------------------------------------------

export interface SalesOrderFilters {
  cursor?: string;
  limit?: number;
  status?: SalesOrderStatus;
  customer_id?: string;
}

export function listSalesOrders(filters: SalesOrderFilters = {}): Promise<Page<SalesOrder>> {
  return api.get<Page<SalesOrder>>("/sales/orders", { params: { ...filters } });
}

export function getSalesOrder(orderId: string): Promise<SalesOrderDetail> {
  return api.get<SalesOrderDetail>(`/sales/orders/${orderId}`);
}

export function createSalesOrder(payload: SalesOrderCreate): Promise<SalesOrderDetail> {
  return api.post<SalesOrderDetail>("/sales/orders", payload, { idempotencyKey: newIdempotencyKey() });
}

export function updateSalesOrder(orderId: string, payload: SalesOrderUpdate): Promise<SalesOrderDetail> {
  return api.patch<SalesOrderDetail>(`/sales/orders/${orderId}`, payload);
}

export function cancelSalesOrder(orderId: string): Promise<SalesOrderDetail> {
  return api.post<SalesOrderDetail>(`/sales/orders/${orderId}/cancel`, undefined);
}

export function confirmSalesOrder(orderId: string): Promise<SalesOrderDetail> {
  return api.post<SalesOrderDetail>(`/sales/orders/${orderId}/confirm`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function releaseSalesOrderCredit(orderId: string): Promise<SalesOrderDetail> {
  return api.post<SalesOrderDetail>(`/sales/orders/${orderId}/credit-release`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function checkAtp(payload: AtpCheckRequest): Promise<AtpCheckResponse> {
  return api.post<AtpCheckResponse>("/sales/orders/atp", payload);
}

// --- Deliveries -----------------------------------------------------------------

export interface DeliveryFilters {
  cursor?: string;
  limit?: number;
  sales_order_id?: string;
  status?: DeliveryStatus;
  date_from?: string;
  date_to?: string;
}

export function listDeliveries(filters: DeliveryFilters = {}): Promise<Page<Delivery>> {
  return api.get<Page<Delivery>>("/sales/deliveries", { params: { ...filters } });
}

export function getDelivery(deliveryId: string): Promise<DeliveryDetail> {
  return api.get<DeliveryDetail>(`/sales/deliveries/${deliveryId}`);
}

export function createDelivery(payload: DeliveryCreate): Promise<DeliveryDetail> {
  return api.post<DeliveryDetail>("/sales/deliveries", payload, { idempotencyKey: newIdempotencyKey() });
}

export function postDelivery(deliveryId: string): Promise<DeliveryDetail> {
  return api.post<DeliveryDetail>(`/sales/deliveries/${deliveryId}/post`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelDelivery(deliveryId: string): Promise<DeliveryDetail> {
  return api.post<DeliveryDetail>(`/sales/deliveries/${deliveryId}/cancel`, undefined);
}
