/**
 * The quote workbench (STRUCTURE §4): edit (DRAFT only), send, accept/reject the customer's
 * response, cancel, or convert to a sales order once accepted. Conversion copies lines/prices/
 * discounts/currency/customer FROZEN from the quote — never re-resolved — mirroring
 * procurement's RFQ→PO conversion.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { StatusPill } from "@/components/StatusPill";
import { useItemLookup, useUomOptions } from "@/modules/inventory/hooks";
import {
  useAcceptQuote,
  useCancelQuote,
  useConvertQuoteToOrder,
  useCustomerOptions,
  useQuote,
  useRejectQuote,
  useSendQuote,
} from "@/modules/sales/hooks";

export function QuoteDetailPage() {
  const { quoteId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.quote.manage");
  const canCreateOrder = (me.data?.permissions ?? []).includes("sales.order.manage");

  const quote = useQuote(quoteId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const customers = useCustomerOptions();
  const sendQuote = useSendQuote(quoteId ?? "");
  const acceptQuote = useAcceptQuote(quoteId ?? "");
  const rejectQuote = useRejectQuote(quoteId ?? "");
  const cancelQuote = useCancelQuote(quoteId ?? "");
  const convertToOrder = useConvertQuoteToOrder(quoteId ?? "");

  const [error, setError] = useState<string | null>(null);
  const [convertedOrderId, setConvertedOrderId] = useState<string | null>(null);

  if (quote.isPending || !quote.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = quote.data;
  const canEdit = data.status === "DRAFT";
  const canSend = data.status === "DRAFT";
  const canAccept = data.status === "SENT";
  const canReject = data.status === "SENT";
  const canCancel = data.status === "DRAFT" || data.status === "SENT" || data.status === "ACCEPTED";
  const canConvert = data.status === "ACCEPTED";

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

  const send = async () => {
    setError(null);
    try {
      await sendQuote.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to send the quote."));
    }
  };

  const accept = async () => {
    setError(null);
    try {
      await acceptQuote.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to accept the quote."));
    }
  };

  const reject = async () => {
    setError(null);
    try {
      await rejectQuote.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to reject the quote."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelQuote.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the quote."));
    }
  };

  const convert = async () => {
    setError(null);
    try {
      const order = await convertToOrder.mutateAsync({});
      setConvertedOrderId(order.id);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to convert the quote to a sales order."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales/quotes">Quotes</Link> / <span className="text-ink">{data.quote_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.quote_number}</h1>
          <div className="flex items-center gap-2.5">
            {canEdit && canManage && (
              <Link
                to="/sales/quotes/$quoteId/edit"
                params={{ quoteId: data.id }}
                className="btn-chip"
              >
                Edit
              </Link>
            )}
            {canCancel && canManage && (
              <button
                type="button"
                onClick={() => void cancel()}
                disabled={cancelQuote.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Cancel
              </button>
            )}
            {canReject && canManage && (
              <button
                type="button"
                onClick={() => void reject()}
                disabled={rejectQuote.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Reject
              </button>
            )}
            {canAccept && canManage && (
              <button
                type="button"
                onClick={() => void accept()}
                disabled={acceptQuote.isPending}
                className="btn-chip"
              >
                {acceptQuote.isPending ? "Accepting…" : "Accept"}
              </button>
            )}
            {canSend && canManage && (
              <button
                type="button"
                onClick={() => void send()}
                disabled={sendQuote.isPending}
                className="btn-ink"
              >
                {sendQuote.isPending ? "Sending…" : "Send"}
              </button>
            )}
            {canConvert && canCreateOrder && (
              <button
                type="button"
                onClick={() => void convert()}
                disabled={convertToOrder.isPending}
                className="btn-ink"
              >
                {convertToOrder.isPending ? "Converting…" : "Convert to order"}
              </button>
            )}
          </div>
        </div>
      </header>

      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {convertedOrderId && (
        <p className="mb-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Sales order created —{" "}
          <Link to="/sales/orders/$orderId" params={{ orderId: convertedOrderId }} className="underline">
            view it
          </Link>
          .
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Status</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            <StatusPill status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Customer</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{customerLabel(data.customer_id)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Valid until</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{data.valid_until ?? "—"}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Total</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{formatMoney(data.total_amount, data.currency_code)}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="py-2 pr-2 text-right">Unit price</th>
            <th className="py-2 pr-2 text-right">Line amount</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(line.uom_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.unit_price, data.currency_code)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatMoney(line.line_amount, data.currency_code)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
