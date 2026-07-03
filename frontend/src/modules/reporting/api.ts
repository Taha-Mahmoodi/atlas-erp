/**
 * Typed endpoint calls for the reporting module only (STRUCTURE §4). The full report-builder
 * surface (entities/run/export) lands with the 15.12 reporting UI; the dashboard is pulled
 * forward because the 15.3 app shell's home page needs it.
 */

import { api } from "@/lib/apiClient";
import type { DashboardResponse } from "@/modules/reporting/types";

export function getDashboard(asOf?: string): Promise<DashboardResponse> {
  return api.get<DashboardResponse>(
    "/reporting/dashboard",
    asOf ? { params: { as_of: asOf } } : undefined,
  );
}
