import { useQuery } from "@tanstack/react-query";

import { listVendors } from "@/modules/procurement/api";

/** All active vendors for a picker (a plain select, not paginated — mirrors
 * finance's useAccountOptions; a searchable combobox is worth adding once a
 * vendor list outgrows one page). */
export function useVendorOptions() {
  return useQuery({
    queryKey: ["procurement", "vendors", "options"],
    queryFn: () => listVendors({ status: "ACTIVE", limit: 200 }),
    staleTime: 60_000,
  });
}
