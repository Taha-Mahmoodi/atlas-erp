/**
 * The leave request workbench (STRUCTURE §4; PLAN 10.2). Lifecycle: DRAFT → submit →
 * SUBMITTED → approve (decrements the balance) / reject; cancel from DRAFT/SUBMITTED (no
 * balance effect) or APPROVED (restores the balance, D-053). Submit/cancel need
 * `hr.leave.request`; approve/reject need the distinct `hr.leave.approve`.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDateTime, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useApproveLeaveRequest,
  useCancelLeaveRequest,
  useEmployeeOptions,
  useLeaveRequest,
  useLeaveTypeOptions,
  useRejectLeaveRequest,
  useSubmitLeaveRequest,
} from "@/modules/hr/hooks";
import { LeaveRequestStatusChip } from "@/modules/hr/pages/LeaveRequestListPage";

const ACTION_BUTTON =
  "rounded-control px-3 py-1.5 text-sm font-medium transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45";
const PRIMARY = `${ACTION_BUTTON} bg-primary text-surface hover:bg-primary-strong`;
const OUTLINE = `${ACTION_BUTTON} border border-line text-ink hover:border-primary hover:text-primary`;
const DANGER_OUTLINE = `${ACTION_BUTTON} border border-line text-ink hover:border-danger hover:text-danger`;

export function LeaveRequestDetailPage() {
  const { requestId } = useParams({ strict: false });
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canRequest = permissions.includes("hr.leave.request");
  const canApprove = permissions.includes("hr.leave.approve");

  const request = useLeaveRequest(requestId);
  const employees = useEmployeeOptions();
  const leaveTypes = useLeaveTypeOptions();
  const submitRequest = useSubmitLeaveRequest(requestId ?? "");
  const approveRequest = useApproveLeaveRequest(requestId ?? "");
  const rejectRequest = useRejectLeaveRequest(requestId ?? "");
  const cancelRequest = useCancelLeaveRequest(requestId ?? "");

  const [decisionNotes, setDecisionNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (request.isPending || !request.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = request.data;

  const employeeLabel = (id: string) => {
    const employee = employees.data?.items.find((e) => e.id === id);
    return employee ? `${employee.employee_code} — ${employee.first_name} ${employee.last_name}` : id;
  };
  const leaveTypeLabel = (id: string) => {
    const leaveType = leaveTypes.data?.items.find((t) => t.id === id);
    return leaveType ? `${leaveType.code} — ${leaveType.name}` : id;
  };

  const act = async (action: () => Promise<unknown>, failure: string) => {
    setError(null);
    try {
      await action();
      setDecisionNotes("");
    } catch (caught) {
      setError(getErrorMessage(caught, failure));
    }
  };

  const busy =
    submitRequest.isPending || approveRequest.isPending || rejectRequest.isPending || cancelRequest.isPending;
  const isDraft = data.status === "DRAFT";
  const isSubmitted = data.status === "SUBMITTED";
  const cancellable = isDraft || isSubmitted || data.status === "APPROVED";
  const notesPayload = decisionNotes ? { notes: decisionNotes } : {};

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.request_number}</h1>
        <div className="flex gap-2">
          {isDraft && canRequest && (
            <>
              <Link
                to="/hr/leave-requests/$requestId/edit"
                params={{ requestId: data.id }}
                className={OUTLINE}
              >
                Edit
              </Link>
              <button
                type="button"
                onClick={() => void act(() => submitRequest.mutateAsync(), "Unable to submit the request.")}
                disabled={busy}
                className={PRIMARY}
              >
                {submitRequest.isPending ? "Submitting…" : "Submit"}
              </button>
            </>
          )}
          {isSubmitted && canApprove && (
            <>
              <button
                type="button"
                onClick={() => void act(() => rejectRequest.mutateAsync(notesPayload), "Unable to reject the request.")}
                disabled={busy}
                className={DANGER_OUTLINE}
              >
                {rejectRequest.isPending ? "Rejecting…" : "Reject"}
              </button>
              <button
                type="button"
                onClick={() => void act(() => approveRequest.mutateAsync(notesPayload), "Unable to approve the request.")}
                disabled={busy}
                className={PRIMARY}
              >
                {approveRequest.isPending ? "Approving…" : "Approve"}
              </button>
            </>
          )}
          {cancellable && canRequest && (
            <button
              type="button"
              onClick={() => void act(() => cancelRequest.mutateAsync(), "Unable to cancel the request.")}
              disabled={busy}
              className={DANGER_OUTLINE}
            >
              {cancelRequest.isPending ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {data.status === "APPROVED" && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Approved — the employee's balance was decremented by {formatQuantity(data.days)} day(s).
          Cancelling now restores it.
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">
            <LeaveRequestStatusChip status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Employee</dt>
          <dd className="text-ink">{employeeLabel(data.employee_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Leave type</dt>
          <dd className="text-ink">{leaveTypeLabel(data.leave_type_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Days</dt>
          <dd className="text-ink tabular-nums">{formatQuantity(data.days)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">From</dt>
          <dd className="text-ink">{data.start_date}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">To</dt>
          <dd className="text-ink">{data.end_date}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Decided</dt>
          <dd className="text-ink">{data.decided_at ? formatDateTime(data.decided_at) : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Reason</dt>
          <dd className="text-ink">{data.reason ?? "—"}</dd>
        </div>
      </dl>

      {data.notes && (
        <div className="mt-4 text-sm">
          <span className="text-xs text-ink-muted">Notes</span>
          <p className="text-ink">{data.notes}</p>
        </div>
      )}

      {isSubmitted && canApprove && (
        <label className="mt-6 block text-xs text-ink-muted">
          Decision note (optional)
          <input
            type="text"
            value={decisionNotes}
            onChange={(event) => setDecisionNotes(event.target.value)}
            className="mt-1 block w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
            placeholder="Recorded on the request with your decision"
          />
        </label>
      )}
    </div>
  );
}
