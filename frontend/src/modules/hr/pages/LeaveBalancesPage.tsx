/**
 * Leave balances + the accrual run (STRUCTURE §4; PLAN 10.2). Pick an employee to see their
 * running balances per leave type; leave-type admins can trigger the idempotent accrual run
 * (grants each ACTIVE employee the per-period amount of each ACTIVE leave type of the chosen
 * frequency, capped — a same-period re-run grants nothing).
 */

import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useEmployeeLeaveBalances,
  useEmployeeOptions,
  useLeaveTypeOptions,
  useRunLeaveAccrual,
} from "@/modules/hr/hooks";
import type { AccrualFrequency } from "@/modules/hr/types";

export function LeaveBalancesPage() {
  const me = useMe();
  const canRunAccrual = (me.data?.permissions ?? []).includes("hr.leave_type.manage");

  const [employeeId, setEmployeeId] = useState("");
  const [frequency, setFrequency] = useState<AccrualFrequency>("MONTHLY");
  const [asOf, setAsOf] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const employees = useEmployeeOptions();
  const leaveTypes = useLeaveTypeOptions();
  const balances = useEmployeeLeaveBalances(employeeId || undefined);
  const runAccrual = useRunLeaveAccrual();

  const leaveTypeLabel = (id: string) => {
    const leaveType = leaveTypes.data?.items.find((t) => t.id === id);
    return leaveType ? `${leaveType.code} — ${leaveType.name}` : id;
  };

  const accrue = async () => {
    setError(null);
    setMessage(null);
    try {
      const result = await runAccrual.mutateAsync({ frequency, ...(asOf ? { asOf } : {}) });
      setMessage(
        `Accrual for ${result.period} (${result.frequency}) granted ${result.balances_accrued} balance${result.balances_accrued === 1 ? "" : "s"}.`,
      );
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to run the accrual."));
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-ink">Leave Balances</h1>

      {canRunAccrual && (
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <h2 className="text-sm font-semibold text-ink">Accrual run</h2>
          <p className="mt-1 text-xs text-ink-muted">
            Grants every active employee the per-period days of each active leave type of this
            frequency. Idempotent — a same-period re-run grants nothing.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <label className="text-xs text-ink-muted">
              Frequency
              <select
                value={frequency}
                onChange={(event) => setFrequency(event.target.value as AccrualFrequency)}
                className="mt-1 block rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              >
                <option value="MONTHLY">Monthly</option>
                <option value="ANNUAL">Annual</option>
              </select>
            </label>
            <label className="text-xs text-ink-muted">
              As of
              <input
                type="date"
                value={asOf}
                onChange={(event) => setAsOf(event.target.value)}
                className="mt-1 block rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
              />
            </label>
            <button
              type="button"
              onClick={() => void accrue()}
              disabled={runAccrual.isPending}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {runAccrual.isPending ? "Running…" : "Run accrual"}
            </button>
          </div>
          {message && <p className="mt-2 rounded-control bg-success-tint px-3 py-2 text-xs text-success">{message}</p>}
          {error && (
            <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
              {error}
            </p>
          )}
        </div>
      )}

      <div className="mt-6">
        <select
          value={employeeId}
          onChange={(event) => setEmployeeId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          aria-label="Employee"
        >
          <option value="">Select an employee…</option>
          {(employees.data?.items ?? []).map((employee) => (
            <option key={employee.id} value={employee.id}>
              {employee.employee_code} — {employee.first_name} {employee.last_name}
            </option>
          ))}
        </select>
      </div>

      {employeeId && (
        <div className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card">
          {balances.isPending ? (
            <p className="text-sm text-ink-muted">Loading…</p>
          ) : (balances.data?.length ?? 0) === 0 ? (
            <p className="text-sm text-ink-muted">No balances yet — run an accrual first.</p>
          ) : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                  <th className="py-2 pr-2">Leave type</th>
                  <th className="py-2 pr-2 text-right">Balance (days)</th>
                  <th className="py-2 pr-2 text-right">Accrued to date</th>
                  <th className="py-2 pr-2 text-right">Taken to date</th>
                  <th className="py-2 pr-2">Last accrual</th>
                </tr>
              </thead>
              <tbody>
                {(balances.data ?? []).map((balance) => (
                  <tr key={balance.id} className="border-b border-line last:border-b-0">
                    <td className="py-1.5 pr-2 text-ink">{leaveTypeLabel(balance.leave_type_id)}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(balance.balance_days)}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(balance.accrued_to_date)}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(balance.taken_to_date)}</td>
                    <td className="py-1.5 pr-2 text-ink-muted">{balance.last_accrual_period ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
