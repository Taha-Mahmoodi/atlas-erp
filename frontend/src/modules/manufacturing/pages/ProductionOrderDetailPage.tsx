/**
 * The production order workbench (STRUCTURE §4): release (reserve materials, DRAFT→RELEASED),
 * issue components to WIP (RELEASED/IN_PROGRESS), finish to stock (IN_PROGRESS), cancel
 * (DRAFT/RELEASED — once components are issued the order must be finished). Components and
 * operations are server-derived at create; issue posts every component's full remaining
 * required quantity from its default bin (per-line partial issue is a backend capability the
 * UI doesn't surface yet).
 */

import { useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import {
  useBinOptions,
  useItemLookup,
  useUomOptions,
  useWarehouseLookup,
} from "@/modules/inventory/hooks";
import { StatusPill } from "@/components/StatusPill";
import {
  useCancelProductionOrder,
  useFinishProductionOrder,
  useIssueComponents,
  useProductionOrder,
  useReleaseProductionOrder,
  useWorkCenterOptions,
} from "@/modules/manufacturing/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function FinishSection({
  orderId,
  warehouseId,
  remainingQuantity,
}: {
  orderId: string;
  warehouseId: string;
  remainingQuantity: string;
}) {
  const bins = useBinOptions(warehouseId);
  const finishOrder = useFinishProductionOrder(orderId);
  const [finishedQuantity, setFinishedQuantity] = useState(remainingQuantity);
  const [binId, setBinId] = useState("");
  const [lotCode, setLotCode] = useState("");
  const [serialCode, setSerialCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setFinishedQuantity(remainingQuantity), [remainingQuantity]);

  const finish = async () => {
    setError(null);
    try {
      await finishOrder.mutateAsync({
        finished_quantity: finishedQuantity,
        finished_bin_id: binId,
        lot_code: lotCode || null,
        serial_code: serialCode || null,
      });
      setLotCode("");
      setSerialCode("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to finish the order."));
    }
  };

  return (
    <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">Finish to stock</h2>
      <p className="mt-1 text-xs text-ink-muted">
        Receives finished goods (Dr Inventory / Cr WIP); the final finish posts the WIP variance so
        WIP nets to zero.
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-3 flex items-end gap-2">
        <div className="w-32">
          <label htmlFor="finish-qty" className="mb-1 block text-xs font-medium text-ink-muted">
            Quantity
          </label>
          <input
            id="finish-qty"
            type="number"
            step="0.000001"
            value={finishedQuantity}
            onChange={(event) => setFinishedQuantity(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="flex-1">
          <label htmlFor="finish-bin" className="mb-1 block text-xs font-medium text-ink-muted">
            Finished-goods bin
          </label>
          <select id="finish-bin" value={binId} onChange={(event) => setBinId(event.target.value)} className={CONTROL}>
            <option value="">Select bin</option>
            {(bins.data?.items ?? []).map((bin) => (
              <option key={bin.id} value={bin.id}>
                {bin.code}
              </option>
            ))}
          </select>
        </div>
        <div className="w-32">
          <label htmlFor="finish-lot" className="mb-1 block text-xs font-medium text-ink-muted">
            Lot (optional)
          </label>
          <input
            id="finish-lot"
            type="text"
            value={lotCode}
            onChange={(event) => setLotCode(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="w-32">
          <label htmlFor="finish-serial" className="mb-1 block text-xs font-medium text-ink-muted">
            Serial (optional)
          </label>
          <input
            id="finish-serial"
            type="text"
            value={serialCode}
            onChange={(event) => setSerialCode(event.target.value)}
            className={CONTROL}
          />
        </div>
        <button
          type="button"
          onClick={() => void finish()}
          disabled={!finishedQuantity || !binId || finishOrder.isPending}
          className="btn-ink"
        >
          {finishOrder.isPending ? "Finishing…" : "Finish"}
        </button>
      </div>
    </div>
  );
}

export function ProductionOrderDetailPage() {
  const { orderId } = useParams({ strict: false });
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("manufacturing.production_order.manage");
  const canRelease = permissions.includes("manufacturing.production_order.release");
  const canExecute = permissions.includes("manufacturing.production_order.execute");

  const order = useProductionOrder(orderId);
  const items = useItemLookup();
  const uoms = useUomOptions();
  const warehouses = useWarehouseLookup();
  const workCenters = useWorkCenterOptions();
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";
  const releaseOrder = useReleaseProductionOrder(orderId ?? "");
  const issueComponents = useIssueComponents(orderId ?? "");
  const cancelOrder = useCancelProductionOrder(orderId ?? "");

  const [error, setError] = useState<string | null>(null);

  if (order.isPending || !order.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = order.data;
  const showRelease = data.status === "DRAFT" && canRelease;
  const showIssue = (data.status === "RELEASED" || data.status === "IN_PROGRESS") && canExecute;
  const showFinish = data.status === "IN_PROGRESS" && canExecute;
  const showCancel = (data.status === "DRAFT" || data.status === "RELEASED") && canManage;
  const hasUnissued = data.components.some(
    (component) => Number(component.issued_quantity) < Number(component.required_quantity),
  );
  const remainingQuantity = String(Number(data.quantity) - Number(data.finished_quantity));

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const uomLabel = (id: string) => {
    const uom = uoms.data?.items.find((u) => u.id === id);
    return uom ? uom.code : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };
  const workCenterLabel = (id: string) => {
    const workCenter = workCenters.data?.items.find((w) => w.id === id);
    return workCenter ? workCenter.code : id;
  };

  const act = async (action: () => Promise<unknown>, fallback: string) => {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(getErrorMessage(caught, fallback));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.order_number}</h1>
          <StatusPill status={data.status} />
        </div>
        <div className="flex gap-2">
          {showCancel && (
            <button
              type="button"
              onClick={() => void act(() => cancelOrder.mutateAsync(), "Unable to cancel the order.")}
              disabled={cancelOrder.isPending}
              className="btn-chip hover:border-danger hover:text-danger"
            >
              Cancel order
            </button>
          )}
          {showIssue && hasUnissued && (
            <button
              type="button"
              onClick={() =>
                void act(() => issueComponents.mutateAsync({}), "Unable to issue the components.")
              }
              disabled={issueComponents.isPending}
              className="btn-ink"
            >
              {issueComponents.isPending ? "Issuing…" : "Issue remaining components"}
            </button>
          )}
          {showRelease && (
            <button
              type="button"
              onClick={() => void act(() => releaseOrder.mutateAsync(), "Unable to release the order.")}
              disabled={releaseOrder.isPending}
              className="btn-ink"
            >
              {releaseOrder.isPending ? "Releasing…" : "Release"}
            </button>
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
          <dt className="text-xs text-ink-muted">Item</dt>
          <dd className="text-ink">{itemLabel(data.item_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Quantity</dt>
          <dd className="text-ink tabular-nums">
            {formatQuantity(data.quantity)} ({formatQuantity(data.finished_quantity)} finished)
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Warehouse</dt>
          <dd className="text-ink">{warehouseLabel(data.warehouse_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">WIP cost</dt>
          <dd className="text-ink tabular-nums">{formatMoney(data.accumulated_wip_cost, currencyCode)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Planned start</dt>
          <dd className="text-ink">{data.planned_start_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Planned end</dt>
          <dd className="text-ink">{data.planned_end_date ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Released</dt>
          <dd className="text-ink">{data.released_at ? data.released_at.slice(0, 10) : "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Finished</dt>
          <dd className="text-ink">{data.finished_at ? data.finished_at.slice(0, 10) : "—"}</dd>
        </div>
      </dl>
      {data.notes && <p className="mt-4 text-sm text-ink-muted">{data.notes}</p>}

      {showFinish && orderId && (
        <FinishSection orderId={orderId} warehouseId={data.warehouse_id} remainingQuantity={remainingQuantity} />
      )}

      <h2 className="mt-8 text-sm font-semibold text-ink">Components</h2>
      <table className="mt-2 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Line</th>
            <th className="py-2 pr-2">Component</th>
            <th className="py-2 pr-2 text-right">Required</th>
            <th className="py-2 pr-2 text-right">Issued</th>
            <th className="py-2 pr-2">UoM</th>
          </tr>
        </thead>
        <tbody>
          {data.components.map((component) => (
            <tr key={component.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{component.line_number}</td>
              <td className="py-1.5 pr-2 text-ink">{itemLabel(component.component_item_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(component.required_quantity)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(component.issued_quantity)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{uomLabel(component.uom_id)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {data.operations.length > 0 && (
        <>
          <h2 className="mt-8 text-sm font-semibold text-ink">Operations</h2>
          <table className="mt-2 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
                <th className="py-2 pr-2">Op</th>
                <th className="py-2 pr-2">Work center</th>
                <th className="py-2 pr-2">Description</th>
                <th className="py-2 pr-2 text-right">Setup (min)</th>
                <th className="py-2 pr-2 text-right">Run (min/unit)</th>
                <th className="py-2 pr-2 text-right">Planned (min)</th>
              </tr>
            </thead>
            <tbody>
              {data.operations.map((operation) => (
                <tr key={operation.id} className="border-b border-line last:border-b-0">
                  <td className="py-1.5 pr-2 text-ink">{operation.operation_number}</td>
                  <td className="py-1.5 pr-2 text-ink">{workCenterLabel(operation.work_center_id)}</td>
                  <td className="py-1.5 pr-2 text-ink-muted">{operation.description ?? "—"}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(operation.setup_time_minutes)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">
                    {formatQuantity(operation.run_time_minutes_per_unit)}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(operation.planned_minutes)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
