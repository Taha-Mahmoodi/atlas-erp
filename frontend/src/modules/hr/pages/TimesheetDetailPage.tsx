/**
 * The timesheet workbench (STRUCTURE §4; PLAN 10.3): time entries with project / cost-center
 * allocation managed inline on a DRAFT (add/remove; the price-list-items precedent), then the
 * lifecycle: DRAFT → submit → SUBMITTED → approve/reject (`hr.timesheet.approve`) or reopen to
 * DRAFT (the backend's cancel verb) for edit + resubmit. Approved hours feed the allocation
 * report. Project is a raw id (the projects module is Phase 11 — the backend stores it
 * unvalidated); cost centers come from finance's reference list.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useAddTimeEntry,
  useApproveTimesheet,
  useCostCenterOptions,
  useEmployeeOptions,
  useRejectTimesheet,
  useRemoveTimeEntry,
  useReopenTimesheet,
  useSubmitTimesheet,
  useTimeEntries,
  useTimesheet,
} from "@/modules/hr/hooks";
import { TimesheetStatusChip } from "@/modules/hr/pages/TimesheetListPage";

const ACTION_BUTTON =
  "rounded-control px-3 py-1.5 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45";
const PRIMARY = `${ACTION_BUTTON} bg-primary text-surface hover:bg-primary-strong`;
const OUTLINE = `${ACTION_BUTTON} border border-line text-ink hover:border-primary hover:text-primary`;
const DANGER_OUTLINE = `${ACTION_BUTTON} border border-line text-ink hover:border-danger hover:text-danger`;
const CELL_INPUT = "w-full rounded-control border border-line bg-surface px-2 py-1 text-[13px] text-ink";

function EntryAddRow({ timesheetId }: { timesheetId: string }) {
  const costCenters = useCostCenterOptions();
  const addEntry = useAddTimeEntry(timesheetId);
  const [entryDate, setEntryDate] = useState("");
  const [hours, setHours] = useState("");
  const [projectId, setProjectId] = useState("");
  const [costCenterId, setCostCenterId] = useState("");
  const [description, setDescription] = useState("");
  const [billable, setBillable] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    setError(null);
    try {
      await addEntry.mutateAsync({
        entry_date: entryDate,
        hours,
        project_id: projectId || null,
        cost_center_id: costCenterId || null,
        task_description: description || null,
        is_billable: billable,
      });
      setEntryDate("");
      setHours("");
      setProjectId("");
      setCostCenterId("");
      setDescription("");
      setBillable(false);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to add the time entry."));
    }
  };

  return (
    <>
      <tr className="border-b border-line">
        <td className="py-1.5 pr-2">
          <input type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)} className={CELL_INPUT} aria-label="Entry date" />
        </td>
        <td className="py-1.5 pr-2">
          <input
            type="number"
            step="0.25"
            min="0"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className={`${CELL_INPUT} text-right`}
            aria-label="Hours"
          />
        </td>
        <td className="py-1.5 pr-2">
          <input
            type="text"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="Project id (optional)"
            className={CELL_INPUT}
            aria-label="Project id"
          />
        </td>
        <td className="py-1.5 pr-2">
          <select value={costCenterId} onChange={(e) => setCostCenterId(e.target.value)} className={CELL_INPUT} aria-label="Cost center">
            <option value="">No cost center</option>
            {(costCenters.data?.items ?? []).map((costCenter) => (
              <option key={costCenter.id} value={costCenter.id}>
                {costCenter.code} — {costCenter.name}
              </option>
            ))}
          </select>
        </td>
        <td className="py-1.5 pr-2">
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Task description"
            className={CELL_INPUT}
            aria-label="Task description"
          />
        </td>
        <td className="py-1.5 pr-2 text-center">
          <input type="checkbox" checked={billable} onChange={(e) => setBillable(e.target.checked)} aria-label="Billable" />
        </td>
        <td className="py-1.5 pr-2 text-right">
          <button
            type="button"
            onClick={() => void add()}
            disabled={addEntry.isPending || !entryDate || !hours}
            className="text-xs font-medium text-primary hover:underline disabled:cursor-not-allowed disabled:opacity-45"
          >
            Add
          </button>
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={7} className="py-1.5 pr-2">
            <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
              {error}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

export function TimesheetDetailPage() {
  const { timesheetId } = useParams({ strict: false });
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("hr.timesheet.manage");
  const canApprove = permissions.includes("hr.timesheet.approve");

  const timesheet = useTimesheet(timesheetId);
  const entries = useTimeEntries(timesheetId);
  const employees = useEmployeeOptions();
  const costCenters = useCostCenterOptions();
  const removeEntry = useRemoveTimeEntry(timesheetId ?? "");
  const submitTimesheet = useSubmitTimesheet(timesheetId ?? "");
  const approveTimesheet = useApproveTimesheet(timesheetId ?? "");
  const rejectTimesheet = useRejectTimesheet(timesheetId ?? "");
  const reopenTimesheet = useReopenTimesheet(timesheetId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (timesheet.isPending || !timesheet.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = timesheet.data;
  const isDraft = data.status === "DRAFT";
  const isSubmitted = data.status === "SUBMITTED";

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

  const busy =
    submitTimesheet.isPending || approveTimesheet.isPending || rejectTimesheet.isPending || reopenTimesheet.isPending;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.timesheet_number}</h1>
        <div className="flex gap-2">
          {isDraft && canManage && (
            <button
              type="button"
              onClick={() => void act(() => submitTimesheet.mutateAsync(), "Unable to submit the timesheet.")}
              disabled={busy}
              className={PRIMARY}
            >
              {submitTimesheet.isPending ? "Submitting…" : "Submit"}
            </button>
          )}
          {isSubmitted && canManage && (
            <button
              type="button"
              onClick={() => void act(() => reopenTimesheet.mutateAsync(), "Unable to reopen the timesheet.")}
              disabled={busy}
              className={OUTLINE}
            >
              {reopenTimesheet.isPending ? "Reopening…" : "Reopen to draft"}
            </button>
          )}
          {isSubmitted && canApprove && (
            <>
              <button
                type="button"
                onClick={() => void act(() => rejectTimesheet.mutateAsync({}), "Unable to reject the timesheet.")}
                disabled={busy}
                className={DANGER_OUTLINE}
              >
                {rejectTimesheet.isPending ? "Rejecting…" : "Reject"}
              </button>
              <button
                type="button"
                onClick={() => void act(() => approveTimesheet.mutateAsync({}), "Unable to approve the timesheet.")}
                disabled={busy}
                className={PRIMARY}
              >
                {approveTimesheet.isPending ? "Approving…" : "Approve"}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">
            <TimesheetStatusChip status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Employee</dt>
          <dd className="text-ink">{employeeLabel(data.employee_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Period</dt>
          <dd className="text-ink">
            {data.period_start} → {data.period_end}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total hours</dt>
          <dd className="text-ink tabular-nums">{formatQuantity(data.total_hours)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Date</th>
            <th className="py-2 pr-2 text-right">Hours</th>
            <th className="py-2 pr-2">Project</th>
            <th className="py-2 pr-2">Cost center</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-center">Billable</th>
            <th className="py-2 pr-2" />
          </tr>
        </thead>
        <tbody>
          {(entries.data ?? []).map((entry) => (
            <tr key={entry.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{entry.entry_date}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(entry.hours)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{entry.project_id ?? "—"}</td>
              <td className="py-1.5 pr-2 text-ink">{entry.cost_center_id ? costCenterLabel(entry.cost_center_id) : "—"}</td>
              <td className="py-1.5 pr-2 text-ink">{entry.task_description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-center">{entry.is_billable ? "Yes" : "No"}</td>
              <td className="py-1.5 pr-2 text-right">
                {isDraft && canManage && (
                  <button
                    type="button"
                    onClick={() => void act(() => removeEntry.mutateAsync(entry.id), "Unable to remove the entry.")}
                    className="text-xs font-medium text-danger hover:underline"
                  >
                    Remove
                  </button>
                )}
              </td>
            </tr>
          ))}
          {isDraft && canManage && timesheetId && <EntryAddRow timesheetId={timesheetId} />}
        </tbody>
      </table>
      {(entries.data?.length ?? 0) === 0 && !isDraft && (
        <p className="mt-2 text-sm text-ink-muted">No time entries.</p>
      )}
    </div>
  );
}
