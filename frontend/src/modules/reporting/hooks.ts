import { useMutation, useQuery } from "@tanstack/react-query";

import { getDashboard, listReportEntities, runReport } from "@/modules/reporting/api";
import type { ReportSpec } from "@/modules/reporting/types";

export function useDashboard(asOf?: string) {
  return useQuery({
    queryKey: ["reporting", "dashboard", asOf ?? null],
    queryFn: () => getDashboard(asOf),
  });
}

export function useReportEntities() {
  return useQuery({
    queryKey: ["reporting", "report-entities"],
    queryFn: () => listReportEntities(),
  });
}

/** A mutation (not a query): a report runs on demand, never refetches in the background. */
export function useRunReport() {
  return useMutation({ mutationFn: (spec: ReportSpec) => runReport(spec) });
}
