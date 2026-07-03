import { useQuery } from "@tanstack/react-query";

import { getDashboard } from "@/modules/reporting/api";

export function useDashboard() {
  return useQuery({
    queryKey: ["reporting", "dashboard"],
    queryFn: () => getDashboard(),
  });
}
