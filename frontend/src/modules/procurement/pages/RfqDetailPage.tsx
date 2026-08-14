/**
 * The RFQ workbench (STRUCTURE §4): send to the vendor, record their quoted unit costs per
 * line, close, or convert to a purchase order once quoted. No approval gate on RFQs — only
 * the resulting PO is a financial commitment.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { StatusPill } from "@/components/StatusPill";
import { useItemLookup, useUomOptions } from "@/modules/inventory/hooks";
import {
  useCloseRfq,
  useConvertRfqToPurchaseOrder,
  useRecordRfqQuote,
  useRfq,
  useSendRfq,
  useVendorLookup,
} from "@/modules/procurement/hooks";

export function RfqDetailPage() {
  const { rfqId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.rfq.manage");
  const canCreatePo = (me.data?.permissions ?? []).includes("procurement.po.manage");

  const rfq = useRfq(rfqId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const vendors = useVendorLookup();
  const sendRfq = useSendRfq(rfqId ?? "");
  const recordQuote = useRecordRfqQuote(rfqId ?? "");
  const closeRfq = useCloseRfq(rfqId ?? "");
  const convertToPo = useConvertRfqToPurchaseOrder(rfqId ?? "");

  const [quoteInputs, setQuoteInputs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [convertedPoId, setConvertedPoId] = useState<string | null>(null);

  if (rfq.isPending || !rfq.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = rfq.data;
  const canSend = data.status === "DRAFT";
  const canRecordQuote = data.status === "SENT";
  const canClose = data.status === "DRAFT" || data.status === "SENT" || data.status === "QUOTED";
  const canConvert = data.status === "QUOTED";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };
  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const send = async () => {
    setError(null);
    try {
      await sendRfq.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to send the RFQ."));
    }
  };

  const saveQuotes = async () => {
    setError(null);
    const quotes = Object.entries(quoteInputs)
      .filter(([, value]) => value)
      .map(([lineId, quotedUnitCost]) => ({ line_id: lineId, quoted_unit_cost: quotedUnitCost }));
    if (quotes.length === 0) return;
    try {
      await recordQuote.mutateAsync({ quotes });
      setQuoteInputs({});
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to record the quotes."));
    }
  };

  const close = async () => {
    setError(null);
    try {
      await closeRfq.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to close the RFQ."));
    }
  };

  const convert = async () => {
    setError(null);
    try {
      const po = await convertToPo.mutateAsync({});
      setConvertedPoId(po.id);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to convert the RFQ to a purchase order."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/procurement/rfqs" className="hover:underline">
            RFQs
          </Link>{" "}
          / <span className="text-ink">{data.rfq_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.rfq_number}</h1>
          <div className="flex items-center gap-2.5">
            {canClose && canManage && (
              <button
                type="button"
                onClick={() => void close()}
                disabled={closeRfq.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Close
              </button>
            )}
            {canSend && canManage && (
              <button
                type="button"
                onClick={() => void send()}
                disabled={sendRfq.isPending}
                className="btn-ink"
              >
                {sendRfq.isPending ? "Sending…" : "Send"}
              </button>
            )}
            {canConvert && canCreatePo && (
              <button
                type="button"
                onClick={() => void convert()}
                disabled={convertToPo.isPending}
                className="btn-ink"
              >
                {convertToPo.isPending ? "Converting…" : "Convert to PO"}
              </button>
            )}
          </div>
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {convertedPoId && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Purchase order created —{" "}
          <Link to="/procurement/purchase-orders/$purchaseOrderId" params={{ purchaseOrderId: convertedPoId }} className="underline">
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
          <dt className="mono-caps text-ink-muted">Vendor</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{vendorLabel(data.vendor_id)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Valid until</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.valid_until ?? "—"}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">UoM</th>
            <th className="py-2 pr-2 text-right">Quoted unit cost</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(line.uom_id)}</td>
              <td className="py-1.5 pr-2 text-right">
                {canRecordQuote && canManage ? (
                  <input
                    type="number"
                    step="0.01"
                    value={quoteInputs[line.id] ?? line.quoted_unit_cost ?? ""}
                    onChange={(event) => setQuoteInputs((prev) => ({ ...prev, [line.id]: event.target.value }))}
                    className="w-28 rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                  />
                ) : (
                  <span className="tabular-nums">{line.quoted_unit_cost ?? "—"}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {canRecordQuote && canManage && (
        <button
          type="button"
          onClick={() => void saveQuotes()}
          disabled={Object.values(quoteInputs).every((v) => !v) || recordQuote.isPending}
          className="mt-4 btn-ink"
        >
          {recordQuote.isPending ? "Saving…" : "Save quotes"}
        </button>
      )}
    </div>
  );
}
