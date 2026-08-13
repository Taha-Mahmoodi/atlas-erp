/**
 * The payroll run workbench (STRUCTURE §4; PLAN 10.4, D-055): post the consolidated finance
 * journal (Dr salary expense by cost center / Cr payroll-tax payable / Cr wages payable —
 * synchronous, same transaction) or cancel a draft. Posting needs the distinct
 * `hr.payroll.post` key; a posted run links its journal entry and is corrected by reversing in
 * finance, never cancelled. `gross = tax + net` per line and in the totals (D-055).
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatMoney, formatPercent } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useCancelPayrollRun,
  useCostCenterOptions,
  useEmployeeOptions,
  usePayrollRun,
  usePostPayrollRun,
} from "@/modules/hr/hooks";
import { PayrollDisclaimer, PayrollRunStatusChip } from "@/modules/hr/pages/PayrollRunListPage";

export function PayrollRunDetailPage() {
  const { runId } = useParams({ strict: false });
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("hr.payroll.manage");
  const canPost = permissions.includes("hr.payroll.post");

  const run = usePayrollRun(runId);
  const employees = useEmployeeOptions();
  const costCenters = useCostCenterOptions();
  const postRun = usePostPayrollRun(runId ?? "");
  const cancelRun = useCancelPayrollRun(runId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (run.isPending || !run.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = run.data;
  const isDraft = data.status === "DRAFT";

  const employeeLabel = (id: string) => {
    const employee = employees.data?.items.find((e) => e.id === id);
    return employee ? `${employee.employee_code} — ${employee.first_name} ${employee.last_name}` : id;
  };
  const costCenterLabel = (id: string) => {
    const costCenter = costCenters.data?.items.find((c) => c.id === id);
    return costCenter ? `${costCenter.code} — ${costCenter.name}` : id;
  };

  const act = async (action: () => Promise<unknown>, failure: string) => {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(getErrorMessage(caught, failure));
    }
  };

  const busy = postRun.isPending || cancelRun.isPending;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.run_number ?? "Draft payroll run"}</h1>
        <div className="flex gap-2">
          {isDraft && canManage && (
            <button
              type="button"
              onClick={() => void act(() => cancelRun.mutateAsync(), "Unable to cancel the run.")}
              disabled={busy}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
            >
              {cancelRun.isPending ? "Cancelling…" : "Cancel"}
            </button>
          )}
          {isDraft && canPost && (
            <button
              type="button"
              onClick={() => void act(() => postRun.mutateAsync({}), "Unable to post the run.")}
              disabled={busy}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {postRun.isPending ? "Posting…" : "Post journal"}
            </button>
          )}
        </div>
      </div>

      <PayrollDisclaimer />

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">
            <PayrollRunStatusChip status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Period</dt>
          <dd className="text-ink">
            {data.period_start} → {data.period_end}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Pay date</dt>
          <dd className="text-ink">{data.pay_date}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Withholding rate</dt>
          <dd className="text-ink tabular-nums">{formatPercent(data.tax_rate_percent)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total gross</dt>
          <dd className="text-ink tabular-nums">{formatMoney(data.total_gross, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total tax</dt>
          <dd className="text-ink tabular-nums">{formatMoney(data.total_tax, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total net</dt>
          <dd className="text-ink tabular-nums">{formatMoney(data.total_net, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Employees</dt>
          <dd className="text-ink tabular-nums">{data.employee_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Posted</dt>
          <dd className="text-ink">{data.posted_at ? formatDateTime(data.posted_at) : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Journal entry</dt>
          <dd className="text-ink">
            {data.journal_entry_id ? (
              <Link
                to="/finance/journal-entries/$entryId"
                params={{ entryId: data.journal_entry_id }}
                className="text-primary hover:underline"
              >
                View journal
              </Link>
            ) : (
              "—"
            )}
          </dd>
        </div>
      </dl>

      {data.notes && (
        <div className="mt-4 text-sm">
          <span className="text-xs text-ink-muted">Notes</span>
          <p className="text-ink">{data.notes}</p>
        </div>
      )}

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Employee</th>
            <th className="py-2 pr-2">Cost center</th>
            <th className="py-2 pr-2 text-right">Gross</th>
            <th className="py-2 pr-2 text-right">Tax</th>
            <th className="py-2 pr-2 text-right">Net</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{employeeLabel(line.employee_id)}</td>
              <td className="py-1.5 pr-2 text-ink">
                {line.cost_center_id ? costCenterLabel(line.cost_center_id) : "—"}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.gross_amount, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.tax_amount, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.net_amount, data.currency_code)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
