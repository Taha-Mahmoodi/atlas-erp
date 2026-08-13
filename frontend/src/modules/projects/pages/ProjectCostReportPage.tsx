/**
 * The project cost report (STRUCTURE §4, D-056): per-WBS actual cost (posted journal lines
 * tagged with the WBS id — time postings and purchases alike), approved hours, budget and
 * variance, rolled up to the project. `as_of` bounds the actuals cumulatively. Amounts are in
 * the tenant's functional currency (the statements precedent).
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney, formatQuantity } from "@/lib/format";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { treeOrder } from "@/modules/projects/components/wbsTree";
import { useProjectCostReport } from "@/modules/projects/hooks";

export function ProjectCostReportPage() {
  const { projectId } = useParams({ strict: false });
  const [asOf, setAsOf] = useState("");

  const currency = useFunctionalCurrency();
  const report = useProjectCostReport(projectId, asOf || undefined);
  const code = currency.data ?? "—";

  if (report.isPending || !report.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = report.data;
  const rows = treeOrder(
    data.lines.map((line) => ({ ...line, id: line.wbs_element_id })),
  );
  const money = (amount: string) => formatMoney(amount, code);
  const varianceTone = (variance: string) => (Number(variance) < 0 ? "text-danger" : "text-ink");

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">
          Cost report — {data.project_code} {data.project_name}
        </h1>
        <Link
          to="/projects/$projectId"
          params={{ projectId: data.project_id }}
          className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-primary"
        >
          Back to project
        </Link>
      </div>

      <div className="mt-4">
        <label htmlFor="as-of" className="mb-1 block text-xs font-medium text-ink-muted">
          Actuals through
        </label>
        <input
          id="as-of"
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
      </div>

      <dl className="mt-6 grid grid-cols-4 gap-4">
        {[
          { label: "Budget", value: money(data.total_budget), tone: "text-ink" },
          { label: "Actual cost", value: money(data.total_actual_cost), tone: "text-ink" },
          { label: "Hours", value: formatQuantity(data.total_hours), tone: "text-ink" },
          { label: "Variance", value: money(data.total_variance), tone: varianceTone(data.total_variance) },
        ].map((kpi) => (
          <div key={kpi.label} className="rounded-card border border-line bg-surface p-4 shadow-card">
            <dt className="text-xs text-ink-muted">{kpi.label}</dt>
            <dd className={`mt-1 text-lg font-semibold tabular-nums ${kpi.tone}`}>{kpi.value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]" aria-label="Costs by WBS element">
          <thead>
            <tr className="border-b border-line bg-panel text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
              <th className="px-3 py-2">WBS</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2 text-right">Budget</th>
              <th className="px-3 py-2 text-right">Actual cost</th>
              <th className="px-3 py-2 text-right">Hours</th>
              <th className="px-3 py-2 text-right">Variance</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-ink-muted">
                  This project has no WBS elements yet — costs can only be collected on WBS elements.
                </td>
              </tr>
            )}
            {rows.map(({ node, depth }) => (
              <tr key={node.wbs_element_id} className="border-b border-line last:border-b-0">
                <td className="px-3 py-1.5 text-ink" style={{ paddingLeft: `${12 + depth * 20}px` }}>
                  {node.code}
                </td>
                <td className="px-3 py-1.5 text-ink">
                  {node.name}
                  {node.status === "CLOSED" && <span className="ml-1.5 text-[11px] text-ink-faint">(closed)</span>}
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{money(node.budget_amount)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{money(node.actual_cost)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{formatQuantity(node.hours)}</td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${varianceTone(node.variance)}`}>
                  {money(node.variance)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
