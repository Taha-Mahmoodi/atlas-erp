/**
 * The reporting dashboard page (PLAN 15.12, D-058): the same role-based KPI card row the shell
 * home page shows, plus an as-of date control for the date-bounded figures (cash / aging / WIP).
 * A pure projection — no actions.
 */

import { useState } from "react";

import { DashboardKpis } from "@/modules/reporting/components/DashboardKpis";
import { useDashboard } from "@/modules/reporting/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DashboardPage() {
  const [asOf, setAsOf] = useState(today());
  const dashboard = useDashboard(asOf);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold text-ink">Dashboard</h1>

      <div className="mt-4 flex items-center gap-2">
        <label htmlFor="dashboard-as-of" className="text-sm text-ink-muted">
          As of
        </label>
        <input
          id="dashboard-as-of"
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
      </div>

      {!dashboard.isPending && Object.keys(dashboard.data ?? {}).length === 0 && (
        <p className="mt-6 text-sm text-ink-muted">
          No KPIs are visible to your role — ask an administrator for reporting access.
        </p>
      )}
      <DashboardKpis data={dashboard.data} loading={dashboard.isPending} />
    </div>
  );
}
