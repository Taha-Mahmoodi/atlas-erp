/**
 * Typed endpoint calls for the reporting module only (STRUCTURE §4): the role-based KPI
 * dashboard (D-058) and the ad-hoc report builder — entities catalog, run, streaming CSV
 * export (D-059). Both surfaces are read-only; the export resolves to a Blob for download.
 */

import { api, postBlob } from "@/lib/apiClient";
import type {
  DashboardResponse,
  ReportEntityList,
  ReportResult,
  ReportSpec,
} from "@/modules/reporting/types";

export function getDashboard(asOf?: string): Promise<DashboardResponse> {
  return api.get<DashboardResponse>(
    "/reporting/dashboard",
    asOf ? { params: { as_of: asOf } } : undefined,
  );
}

/** The role-filtered report-builder catalog — only entities the caller may report on. */
export function listReportEntities(): Promise<ReportEntityList> {
  return api.get<ReportEntityList>("/reporting/reports/entities");
}

/** Run an ad-hoc report to the JSON grid (capped at 10k rows, truncation flagged). */
export function runReport(spec: ReportSpec): Promise<ReportResult> {
  return api.post<ReportResult>("/reporting/reports/run", spec);
}

/** The same spec as a streaming CSV export — the path for results beyond the 10k grid cap. */
export function exportReportCsv(spec: ReportSpec): Promise<Blob> {
  return postBlob("/reporting/reports/export", spec);
}
