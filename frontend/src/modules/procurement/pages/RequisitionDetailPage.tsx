/**
 * The requisition workbench (STRUCTURE §4): view lines, submit for approval, decide
 * (approve/reject), cancel, edit while still DRAFT. Submit auto-advances straight to APPROVED
 * when no REQUISITION approval rule applies to the line total (or the rule's currency doesn't
 * match) — there's no separate decision step in that case, so this page doesn't assume
 * SUBMITTED always follows submit.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup, useUomOptions } from "@/modules/inventory/hooks";
import {
  useCancelRequisition,
  useDecideRequisition,
  useRequisition,
  useSubmitRequisition,
} from "@/modules/procurement/hooks";

export function RequisitionDetailPage() {
  const { requisitionId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.requisition.manage");
  const canApprove = (me.data?.permissions ?? []).includes("procurement.requisition.approve");

  const requisition = useRequisition(requisitionId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const submitRequisition = useSubmitRequisition(requisitionId ?? "");
  const decideRequisition = useDecideRequisition(requisitionId ?? "");
  const cancelRequisition = useCancelRequisition(requisitionId ?? "");

  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (requisition.isPending || !requisition.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = requisition.data;
  const isDraft = data.status === "DRAFT";
  const isSubmitted = data.status === "SUBMITTED";
  const canCancel = data.status === "DRAFT" || data.status === "APPROVED";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };

  const submit = async () => {
    setError(null);
    try {
      await submitRequisition.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to submit the requisition."));
    }
  };

  const decide = async (decision: "APPROVED" | "REJECTED") => {
    setError(null);
    try {
      await decideRequisition.mutateAsync({ decision, comment: comment || null });
      setComment("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to record the decision."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelRequisition.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the requisition."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">{data.requisition_number}</h1>
        <div className="flex gap-2">
          {isDraft && canManage && (
            <Link
              to="/procurement/requisitions/$requisitionId/edit"
              params={{ requisitionId: data.id }}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-primary"
            >
              Edit
            </Link>
          )}
          {canCancel && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelRequisition.isPending}
              className="rounded-control border border-line px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-150 hover:border-danger hover:text-danger disabled:cursor-not-allowed disabled:opacity-45"
            >
              Cancel
            </button>
          )}
          {isDraft && canManage && (
            <button
              type="button"
              onClick={() => void submit()}
              disabled={submitRequisition.isPending}
              className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
            >
              {submitRequisition.isPending ? "Submitting…" : "Submit"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Needed by</dt>
          <dd className="text-ink">{data.needed_by_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Notes</dt>
          <dd className="text-ink">{data.notes ?? "—"}</dd>
        </div>
      </dl>

      {isSubmitted && canApprove && (
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <h2 className="text-sm font-semibold text-ink">Decision</h2>
          <label htmlFor="comment" className="mb-1 mt-3 block text-xs font-medium text-ink-muted">
            Comment (optional)
          </label>
          <textarea
            id="comment"
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          />
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => void decide("APPROVED")}
              disabled={decideRequisition.isPending}
              className="rounded-control bg-success px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => void decide("REJECTED")}
              disabled={decideRequisition.isPending}
              className="rounded-control bg-danger px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="py-2 pr-2 text-right">Est. unit cost</th>
            <th className="py-2 pr-2">Currency</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(line.uom_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {line.estimated_unit_cost ? formatQuantity(line.estimated_unit_cost) : "—"}
              </td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.currency_code}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
