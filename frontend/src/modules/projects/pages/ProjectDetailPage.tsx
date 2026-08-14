/**
 * The project workbench (STRUCTURE §4): header facts, the WBS elements panel (tree + inline
 * form), and the door to the cost report. Editing the header lives on `/edit`.
 */

import { Link, useParams } from "@tanstack/react-router";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { WbsPanel } from "@/modules/projects/components/WbsPanel";
import { useProject } from "@/modules/projects/hooks";
import { useCustomerOptions } from "@/modules/sales/hooks";
import { StatusPill } from "@/components/StatusPill";

export function ProjectDetailPage() {
  const { projectId } = useParams({ strict: false });
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("projects.project.manage");
  const canManageWbs = permissions.includes("projects.wbs.manage");
  const canReadReport = permissions.includes("projects.report.read");

  const project = useProject(projectId);
  const currency = useFunctionalCurrency();
  const customers = useCustomerOptions();

  if (project.isPending || !project.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = project.data;
  const customer = customers.data?.items.find((entry) => entry.id === data.customer_id);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {data.code} — {data.name}
          <StatusPill status={data.status} />
        </h1>
        <div className="flex gap-2">
          {canReadReport && (
            <Link
              to="/projects/$projectId/cost-report"
              params={{ projectId: data.id }}
              className="btn-chip"
            >
              Cost report
            </Link>
          )}
          {canManage && (
            <Link
              to="/projects/$projectId/edit"
              params={{ projectId: data.id }}
              className="btn-chip"
            >
              Edit
            </Link>
          )}
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Customer</dt>
          <dd className="text-ink">
            {customer ? `${customer.customer_code} — ${customer.name}` : (data.customer_id ?? "—")}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Start</dt>
          <dd className="text-ink">{data.start_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">End</dt>
          <dd className="text-ink">{data.end_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Budget</dt>
          <dd className="text-ink tabular-nums">
            {data.budget_amount === null ? "—" : formatMoney(data.budget_amount, currency.data ?? "—")}
          </dd>
        </div>
        {data.description && (
          <div className="col-span-4">
            <dt className="text-xs text-ink-muted">Description</dt>
            <dd className="text-ink">{data.description}</dd>
          </div>
        )}
      </dl>

      <div className="mt-8">
        <WbsPanel projectId={data.id} canManage={canManageWbs} />
      </div>
    </div>
  );
}
