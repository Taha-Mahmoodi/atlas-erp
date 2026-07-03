import { api, type Page } from "@/lib/apiClient";
import type { Customer } from "@/modules/sales/types";

export function listCustomers(params: { limit?: number; status?: string } = {}): Promise<Page<Customer>> {
  return api.get<Page<Customer>>("/sales/customers", { params });
}
