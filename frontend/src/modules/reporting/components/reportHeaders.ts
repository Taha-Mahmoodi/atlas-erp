/**
 * The results grid's column headers (#166). Pure mapping, no JSX — it lives here rather than in
 * ReportBuilderPage.tsx because that page is already over STRUCTURE §8.4's 300-line TSX cap (#176).
 */

import type { ReportResult } from "@/modules/reporting/types";

/** The header for each result column (#166): the backend's display label, falling back to the wire
 * name when a label is missing (a pre-#166 server, or a stale cached response). The CSV export
 * writes the very same labels server-side, so the two surfaces cannot drift apart. */
export function resultHeaders(
  result?: Pick<ReportResult, "columns" | "column_labels">,
): string[] {
  const labels = result?.column_labels ?? [];
  return (result?.columns ?? []).map((name, index) => labels[index] ?? name);
}
