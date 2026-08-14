/**
 * The reporting org chart (STRUCTURE §4; PLAN 10.1, D-052): a simple indented tree render of
 * the structural snapshot (name/code/title only — the backend never carries compensation here).
 * Optionally anchored on a single employee's sub-tree.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { useEmployeeOptions, useOrgChart, usePositionOptions } from "@/modules/hr/hooks";
import type { OrgChartNode } from "@/modules/hr/types";

function TreeNode({ node, positionLabel }: { node: OrgChartNode; positionLabel: (id: string) => string }) {
  return (
    <li>
      <div className="flex items-baseline gap-2 border-l-2 border-line py-1.5 pl-3">
        <Link
          to="/hr/employees/$employeeId"
          params={{ employeeId: node.id }}
          className="text-sm font-medium text-ink hover:text-primary hover:underline"
        >
          {node.first_name} {node.last_name}
        </Link>
        <span className="text-xs text-ink-muted">{node.employee_code}</span>
        {node.position_id && <span className="text-xs text-ink-faint">{positionLabel(node.position_id)}</span>}
      </div>
      {node.reports.length > 0 && (
        <ul className="ml-5">
          {node.reports.map((report) => (
            <TreeNode key={report.id} node={report} positionLabel={positionLabel} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function OrgChartPage() {
  const [rootEmployeeId, setRootEmployeeId] = useState("");
  const chart = useOrgChart(rootEmployeeId || undefined);
  const employees = useEmployeeOptions();
  const positions = usePositionOptions();

  const positionLabel = (id: string) => {
    const position = positions.data?.items.find((p) => p.id === id);
    return position ? position.title : "";
  };

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hr">HR</Link> / <span className="text-ink">Org chart</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Org Chart</h1>
          <div className="flex items-center gap-2.5">
            <select
              value={rootEmployeeId}
              onChange={(event) => setRootEmployeeId(event.target.value)}
              className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              aria-label="Anchor on employee"
            >
              <option value="">Whole organization</option>
              {(employees.data?.items ?? []).map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.employee_code} — {employee.first_name} {employee.last_name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </header>

      <div className="rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
        {chart.isPending ? (
          <p className="text-[13px] text-ink-muted">Loading…</p>
        ) : (chart.data?.roots.length ?? 0) === 0 ? (
          <p className="text-[13px] text-ink-muted">No employees in the reporting tree.</p>
        ) : (
          <ul>
            {chart.data?.roots.map((root) => (
              <TreeNode key={root.id} node={root} positionLabel={positionLabel} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
