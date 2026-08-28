/**
 * The delivery workbench (STRUCTURE §4): post or cancel a draft delivery. Posting is
 * synchronous, not a background job — it publishes DeliveryShipped in the same transaction,
 * which inventory turns into a stock ISSUE move per line and finance posts the COGS journal
 * for. POSTED is terminal (corrections happen via a return in a later slice); CANCELLED only
 * from DRAFT.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useDocumentFlow } from "@/lib/docflow";
import { formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DocFlowViewer } from "@/components/DocFlowViewer";
import { StatusPill } from "@/components/StatusPill";
import { useBinLookup, useItemLookup, useWarehouseLookup } from "@/modules/inventory/hooks";
import { useCancelDelivery, useCustomerOptions, useDelivery, usePostDelivery } from "@/modules/sales/hooks";

export function DeliveryDetailPage() {
  const { deliveryId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.delivery.manage");
  const canPost = (me.data?.permissions ?? []).includes("sales.delivery.post");

  const delivery = useDelivery(deliveryId);
  const items = useItemLookup();
  const bins = useBinLookup();
  const customers = useCustomerOptions();
  const warehouses = useWarehouseLookup();
  const postDelivery = usePostDelivery(deliveryId ?? "");
  const cancelDelivery = useCancelDelivery(deliveryId ?? "");
  const flow = useDocumentFlow(delivery.data?.document_id);

  const [error, setError] = useState<string | null>(null);

  if (delivery.isPending || !delivery.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = delivery.data;
  const isDraft = data.status === "DRAFT";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const binLabel = (id: string) => {
    const bin = bins.data?.items.find((b) => b.id === id);
    return bin ? bin.code : id;
  };
  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const post = async () => {
    setError(null);
    try {
      await postDelivery.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to post the delivery."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelDelivery.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the delivery."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales/deliveries">Deliveries</Link> / <span className="text-ink">{data.delivery_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.delivery_number}</h1>
          <div className="flex items-center gap-2.5">
            {isDraft && canManage && (
              <button
                type="button"
                onClick={() => void cancel()}
                disabled={cancelDelivery.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Cancel
              </button>
            )}
            {isDraft && canPost && (
              <button
                type="button"
                onClick={() => void post()}
                disabled={postDelivery.isPending}
                className="btn-ink"
              >
                {postDelivery.isPending ? "Posting…" : "Post"}
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
          <dt className="mono-caps text-ink-muted">Warehouse</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{warehouseLabel(data.warehouse_id)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Delivery date</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{data.delivery_date}</dd>
        </div>
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Bin</th>
            <th className="py-2 pr-2 text-right">Quantity</th>
            <th className="py-2 pr-2">Lot / serial</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{binLabel(line.bin_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.lot_code ?? line.serial_code ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="mt-8">
        <h2 className="mb-3.5 mono-caps text-ink-muted">Document flow</h2>
        <DocFlowViewer {...flow} />
      </section>
    </div>
  );
}
