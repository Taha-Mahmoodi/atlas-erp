import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createCustomer,
  createCustomerGroup,
  type CustomerFilters,
  type CustomerGroupFilters,
  getCustomer,
  getCustomerGroup,
  listCustomerGroups,
  listCustomers,
  updateCustomer,
  updateCustomerGroup,
} from "@/modules/sales/api";
import type {
  CustomerCreate,
  CustomerGroupCreate,
  CustomerGroupUpdate,
  CustomerUpdate,
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
