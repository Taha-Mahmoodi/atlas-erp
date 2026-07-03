import { useQuery } from "@tanstack/react-query";

import { listCustomers } from "@/modules/sales/api";

/** All active customers for a picker (mirrors procurement's useVendorOptions). */
export function useCustomerOptions() {
  return useQuery({
    queryKey: ["sales", "customers", "options"],
    queryFn: () => listCustomers({ status: "ACTIVE", limit: 200 }),
    staleTime: 60_000,
  });
}
