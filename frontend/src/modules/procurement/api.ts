import { api, type Page } from "@/lib/apiClient";
import type { Vendor } from "@/modules/procurement/types";

export function listVendors(params: { limit?: number; status?: string } = {}): Promise<Page<Vendor>> {
  return api.get<Page<Vendor>>("/procurement/vendors", { params });
}
