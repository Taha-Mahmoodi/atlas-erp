import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCustomer,
  createCustomerGroup,
  createPriceList,
  createPriceListItem,
  type CustomerFilters,
  type CustomerGroupFilters,
  deletePriceListItem,
  getCustomer,
  getCustomerGroup,
  getPriceList,
  getPriceQuote,
  listCustomerGroups,
  listCustomers,
  listPriceListItems,
  listPriceLists,
  type PriceListFilters,
  type PriceQuoteParams,
  updateCustomer,
  updateCustomerGroup,
  updatePriceList,
} from "@/modules/sales/api";
import type {
  CustomerCreate,
  CustomerGroupCreate,
  CustomerGroupUpdate,
  CustomerUpdate,
  PriceListCreate,
  PriceListItemCreate,
  PriceListUpdate,
} from "@/modules/sales/types";

/** All active customers for a picker (mirrors procurement's useVendorOptions). Predates this
 * slice — finance's AR workbench (receipts, invoices, aging, dunning) already depends on this
 * exact hook; kept unchanged so those pages keep working. */
export function useCustomerOptions() {
  return useQuery({
    queryKey: ["sales", "customers", "options"],
    queryFn: () => listCustomers({ status: "ACTIVE", limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCustomers(filters: Omit<CustomerFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "customers", filters],
    queryFn: ({ pageParam }) => listCustomers({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useCustomer(customerId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "customer", customerId],
    queryFn: () => getCustomer(customerId as string),
    enabled: customerId !== undefined,
  });
}

function invalidateCustomers(queryClient: ReturnType<typeof useQueryClient>, customerId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "customers"] });
  if (customerId) void queryClient.invalidateQueries({ queryKey: ["sales", "customer", customerId] });
}

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerCreate) => createCustomer(payload),
    onSuccess: () => invalidateCustomers(queryClient),
  });
}

export function useUpdateCustomer(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerUpdate) => updateCustomer(customerId, payload),
    onSuccess: () => invalidateCustomers(queryClient, customerId),
  });
}

// --- Customer groups -------------------------------------------------------------

export function useCustomerGroups(filters: CustomerGroupFilters = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "customer-groups", filters],
    queryFn: ({ pageParam }) =>
      listCustomerGroups({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All customer groups for a picker (a price list or customer's group dropdown). */
export function useCustomerGroupOptions() {
  return useQuery({
    queryKey: ["sales", "customer-groups", "options"],
    queryFn: () => listCustomerGroups({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCustomerGroup(customerGroupId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "customer-group", customerGroupId],
    queryFn: () => getCustomerGroup(customerGroupId as string),
    enabled: customerGroupId !== undefined,
  });
}

function invalidateCustomerGroups(queryClient: ReturnType<typeof useQueryClient>, customerGroupId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "customer-groups"] });
  if (customerGroupId) {
    void queryClient.invalidateQueries({ queryKey: ["sales", "customer-group", customerGroupId] });
  }
}

export function useCreateCustomerGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerGroupCreate) => createCustomerGroup(payload),
    onSuccess: () => invalidateCustomerGroups(queryClient),
  });
}

export function useUpdateCustomerGroup(customerGroupId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CustomerGroupUpdate) => updateCustomerGroup(customerGroupId, payload),
    onSuccess: () => invalidateCustomerGroups(queryClient, customerGroupId),
  });
}

// --- Price lists ------------------------------------------------------------------

export function usePriceLists(filters: Omit<PriceListFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["sales", "price-lists", filters],
    queryFn: ({ pageParam }) => listPriceLists({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function usePriceList(priceListId: string | undefined) {
  return useQuery({
    queryKey: ["sales", "price-list", priceListId],
    queryFn: () => getPriceList(priceListId as string),
    enabled: priceListId !== undefined,
  });
}

function invalidatePriceLists(queryClient: ReturnType<typeof useQueryClient>, priceListId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["sales", "price-lists"] });
  if (priceListId) void queryClient.invalidateQueries({ queryKey: ["sales", "price-list", priceListId] });
}

export function useCreatePriceList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListCreate) => createPriceList(payload),
    onSuccess: () => invalidatePriceLists(queryClient),
  });
}

export function useUpdatePriceList(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListUpdate) => updatePriceList(priceListId, payload),
    onSuccess: () => invalidatePriceLists(queryClient, priceListId),
  });
}

export function usePriceListItems(priceListId: string) {
  return useQuery({
    queryKey: ["sales", "price-list-items", priceListId],
    queryFn: () => listPriceListItems(priceListId),
  });
}

export function useCreatePriceListItem(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PriceListItemCreate) => createPriceListItem(priceListId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "price-list-items", priceListId] }),
  });
}

export function useDeletePriceListItem(priceListId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deletePriceListItem(priceListId, itemId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["sales", "price-list-items", priceListId] }),
  });
}

// --- Price quote (read-only simulation, no persisted document) --------------------

export function usePriceQuote(params: PriceQuoteParams | undefined) {
  return useQuery({
    queryKey: ["sales", "price-quote", params],
    queryFn: () => getPriceQuote(params as PriceQuoteParams),
    enabled: params !== undefined,
  });
}
