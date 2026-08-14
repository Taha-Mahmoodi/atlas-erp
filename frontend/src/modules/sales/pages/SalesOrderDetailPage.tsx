/**
 * The sales order workbench (STRUCTURE §4): edit (DRAFT only), confirm, cancel, and an
 * on-demand ATP availability check. Confirmation runs two independent checks — ATP (never
 * blocks; a shortfall just flags backordered=true per line) and credit (a HARD block: over the
 * customer's limit sets the order to CREDIT_BLOCKED, a 200 business outcome, not an error).
 * A CREDIT_BLOCKED order only recovers via "Release credit hold", which marks the hold
 * released and re-confirms in one step, skipping the credit gate this time.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup, useUomOptions } from "@/modules/inventory/hooks";
import {
  useCancelSalesOrder,
  useCheckAtp,
  useConfirmSalesOrder,
  useCustomerOptions,
  useReleaseSalesOrderCredit,
  useSalesOrder,
} from "@/modules/sales/hooks";
import type { AtpLineResult } from "@/modules/sales/types";
import { StatusPill } from "@/components/StatusPill";

export function SalesOrderDetailPage() {
  const { orderId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.order.manage");
  const canConfirm = (me.data?.permissions ?? []).includes("sales.order.confirm");
  const canReleaseCredit = (me.data?.permissions ?? []).includes("sales.order.credit_release");

  const order = useSalesOrder(orderId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const customers = useCustomerOptions();
  const confirmOrder = useConfirmSalesOrder(orderId ?? "");
  const cancelOrder = useCancelSalesOrder(orderId ?? "");
  const releaseCredit = useReleaseSalesOrderCredit(orderId ?? "");
  const checkAtp = useCheckAtp();

  const [error, setError] = useState<string | null>(null);
  const [atpResults, setAtpResults] = useState<AtpLineResult[] | null>(null);

  if (order.isPending || !order.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = order.data;
  const isDraft = data.status === "DRAFT";
  const isCreditBlocked = data.status === "CREDIT_BLOCKED";
  const canEdit = isDraft;
  const canCancel = isDraft;
  const canConfirmNow = isDraft && canConfirm;
  const canReleaseNow = isCreditBlocked && canReleaseCredit;

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };
  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const confirm = async () => {
    setError(null);
    try {
      await confirmOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to confirm the sales order."));
    }
  };

  const release = async () => {
    setError(null);
    try {
      await releaseCredit.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to release the credit hold."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelOrder.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the sales order."));
    }
  };

  const checkAvailability = async () => {
    setError(null);
    try {
      const result = await checkAtp.mutateAsync({
        lines: data.lines.map((line) => ({ item_id: line.item_id, quantity: line.ordered_quantity })),
      });
      setAtpResults(result.lines);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to check availability."));
    }
  };

  const atpForLine = (itemId: string) => atpResults?.find((line) => line.item_id === itemId);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.order_number}</h1>
        <div className="flex gap-2">
          {canEdit && canManage && (
            <Link
              to="/sales/orders/$orderId/edit"
              params={{ orderId: data.id }}
              className="btn-chip"
            >
              Edit
            </Link>
          )}
          {canCancel && canManage && (
            <button
              type="button"
              onClick={() => void cancel()}
              disabled={cancelOrder.isPending}
              className="btn-chip hover:border-danger hover:text-danger"
            >
              Cancel
            </button>
          )}
          <button
            type="button"
            onClick={() => void checkAvailability()}
            disabled={checkAtp.isPending}
            className="btn-chip"
          >
            {checkAtp.isPending ? "Checking…" : "Check availability"}
          </button>
          {canReleaseNow && (
            <button
              type="button"
              onClick={() => void release()}
              disabled={releaseCredit.isPending}
              className="btn-ink"
            >
              {releaseCredit.isPending ? "Releasing…" : "Release credit hold"}
            </button>
          )}
          {canConfirmNow && (
            <button
              type="button"
              onClick={() => void confirm()}
              disabled={confirmOrder.isPending}
              className="btn-ink"
            >
              {confirmOrder.isPending ? "Confirming…" : "Confirm"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {isCreditBlocked && (
        <p className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          This order exceeds the customer's credit limit and is on hold. Release the hold to confirm anyway.
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Customer</dt>
          <dd className="text-ink">{customerLabel(data.customer_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Credit check</dt>
          <dd className="text-ink">{data.credit_check_status ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Total</dt>
          <dd className="text-ink">{formatMoney(data.total_amount, data.currency_code)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="py-2 pr-2 text-right">Unit price</th>
            <th className="py-2 pr-2 text-right">Line amount</th>
            {atpResults && <th className="py-2 pr-2">Availability</th>}
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => {
            const atp = atpForLine(line.item_id);
            return (
              <tr key={line.id} className="border-b border-line last:border-b-0">
                <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.ordered_quantity)}</td>
                <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(line.uom_id)}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_price, data.currency_code)}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.line_amount, data.currency_code)}</td>
                {atpResults && (
                  <td className="py-1.5 pr-2">
                    {atp ? (
                      <StatusPill
                        status={atp.backordered ? "PARTIALLY_DELIVERED" : "ACTIVE"}
                        label={
                          atp.backordered
                            ? `Backordered (${formatQuantity(atp.shortfall)} short)`
                            : "Available"
                        }
                      />
                    ) : (
                      "—"
                    )}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
