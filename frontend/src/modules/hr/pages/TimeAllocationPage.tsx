/**
 * The time allocation report (STRUCTURE §4; PLAN 10.3): APPROVED hours grouped by cost center
 * or project over a date range — the report payroll costing and project costing read from.
 * Project rows show the raw id (the projects module is Phase 11).
 */

import { useState } from "react";

import { formatQuantity } from "@/lib/format";
import { useCostCenterOptions, useTimeAllocation } from "@/modules/hr/hooks";
import type { AllocationDimension } from "@/modules/hr/types";

export function TimeAllocationPage() {
  const [by, setBy] = useState<AllocationDimension>("cost_center");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const costCenters = useCostCenterOptions();
  const report = useTimeAllocation(by, dateFrom || undefined, dateTo || undefined);

  const dimensionLabel = (id: string | null) => {
    if (id === null) return "Unallocated";
    if (by === "project") return id;
    const costCenter = costCenters.data?.items.find((c) => c.id === id);
    return costCenter ? `${costCenter.code} — ${costCenter.name}` : id;
  };

  const rows = report.data?.rows ?? [];
  const totalHours = rows.reduce((sum, row) => sum + Number(row.hours), 0);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-ink">Time Allocation</h1>
      <p className="mt-1 text-sm text-ink-muted">Approved hours grouped by cost center or project.</p>

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <label className="text-xs text-ink-muted">
          Group by
          <select
            value={by}
            onChange={(event) => setBy(event.target.value as AllocationDimension)}
            className="mt-1 block rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="cost_center">Cost center</option>
            <option value="project">Project</option>
          </select>
        </label>
        <label className="text-xs text-ink-muted">
          From
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
            className="mt-1 block rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </label>
        <label className="text-xs text-ink-muted">
          To
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
            className="mt-1 block rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
        </label>
      </div>

      <div className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card">
        {!dateFrom || !dateTo ? (
          <p className="text-sm text-ink-muted">Pick a date range to run the report.</p>
        ) : report.isPending ? (
          <p className="text-sm text-ink-muted">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-ink-muted">No approved hours in this range.</p>
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                <th className="py-2 pr-2">{by === "project" ? "Project" : "Cost center"}</th>
                <th className="py-2 pr-2 text-right">Hours</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.dimension_id ?? "none"} className="border-b border-line">
                  <td className="py-1.5 pr-2 text-ink">{dimensionLabel(row.dimension_id)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(row.hours)}</td>
                </tr>
              ))}
              <tr>
                <td className="py-1.5 pr-2 text-xs font-semibold uppercase tracking-[0.02em] text-ink-muted">Total</td>
                <td className="py-1.5 pr-2 text-right font-semibold tabular-nums text-ink">
                  {formatQuantity(totalHours)}
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
