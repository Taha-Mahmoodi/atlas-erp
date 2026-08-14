/**
 * MRP run results (STRUCTURE §4): the run header, the rough-capacity check per work center
 * (overloaded rows flagged), and the paginated planned-orders grid with firm / convert /
 * cancel actions. Convert turns a MAKE order into a production order and a BUY order into a
 * procurement requisition; a MAKE convert on an unscoped run needs a warehouse picked here.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatPercent, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup, useWarehouseOptions } from "@/modules/inventory/hooks";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import {
  useCancelPlannedOrder,
  useConvertPlannedOrder,
  useFirmPlannedOrder,
  useMrpRun,
  usePlannedOrders,
  useWorkCenterOptions,
} from "@/modules/manufacturing/hooks";
import type {
  PlannedOrder,
  PlannedOrderStatus,
  PlannedOrderType,
} from "@/modules/manufacturing/types";

export function MrpRunDetailPage() {
  const { runId } = useParams({ strict: false });
  const me = useMe();
  const canManagePlanned = (me.data?.permissions ?? []).includes("manufacturing.planned_order.manage");

  const run = useMrpRun(runId);
  const items = useItemLookup();
  const workCenters = useWorkCenterOptions();
  const warehouses = useWarehouseOptions();
  const [orderType, setOrderType] = useState<PlannedOrderType | "">("");
  const [status, setStatus] = useState<PlannedOrderStatus | "">("");
  const [convertWarehouseId, setConvertWarehouseId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const plannedOrders = usePlannedOrders(runId, {
    ...(orderType ? { order_type: orderType } : {}),
    ...(status ? { status } : {}),
  });
  const firmOrder = useFirmPlannedOrder(runId ?? "");
  const convertOrder = useConvertPlannedOrder(runId ?? "");
  const cancelOrder = useCancelPlannedOrder(runId ?? "");

  if (run.isPending || !run.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = run.data;
  const rows = plannedOrders.data?.pages.flatMap((page) => page.items) ?? [];
  // Only unscoped runs need a warehouse picked for MAKE converts (D-049).
  const needsConvertWarehouse = data.warehouse_id === null;

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const workCenterLabel = (id: string) => {
    const workCenter = workCenters.data?.items.find((w) => w.id === id);
    return workCenter ? `${workCenter.code} — ${workCenter.name}` : id;
  };

  const act = async (action: () => Promise<unknown>, fallback: string) => {
    setError(null);
    try {
      await action();
    } catch (caught) {
      setError(getErrorMessage(caught, fallback));
    }
  };

  const actionsBusy = firmOrder.isPending || convertOrder.isPending || cancelOrder.isPending;

  const columns: DataGridColumn<PlannedOrder>[] = [
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    { key: "order_type", header: "Type", render: (row) => row.order_type, width: "70px" },
    {
      key: "quantity",
      header: "Quantity",
      align: "right",
      render: (row) => formatQuantity(row.quantity),
      width: "100px",
    },
    { key: "due_date", header: "Due", render: (row) => row.due_date ?? "—", width: "100px" },
    { key: "level", header: "Level", align: "right", render: (row) => String(row.level), width: "70px" },
    {
      key: "status",
      header: "Status",
      render: (row) => (
        <StatusPill status={row.status} />
      ),
      width: "110px",
    },
    ...(canManagePlanned
      ? [
          {
            key: "actions",
            header: "",
            render: (row: PlannedOrder) =>
              row.status === "PLANNED" || row.status === "FIRMED" ? (
                <span className="flex gap-2">
                  {row.status === "PLANNED" && (
                    <button
                      type="button"
                      onClick={() => void act(() => firmOrder.mutateAsync(row.id), "Unable to firm the planned order.")}
                      disabled={actionsBusy}
                      className="text-[12.5px] font-medium text-primary hover:underline disabled:opacity-45"
                    >
                      Firm
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() =>
                      void act(
                        () =>
                          convertOrder.mutateAsync({
                            plannedOrderId: row.id,
                            payload: { warehouse_id: convertWarehouseId || null },
                          }),
                        "Unable to convert the planned order.",
                      )
                    }
                    disabled={actionsBusy}
                    className="text-[12.5px] font-medium text-primary hover:underline disabled:opacity-45"
                  >
                    Convert
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      void act(() => cancelOrder.mutateAsync(row.id), "Unable to cancel the planned order.")
                    }
                    disabled={actionsBusy}
                    className="text-[12.5px] font-medium text-danger hover:underline disabled:opacity-45"
                  >
                    Cancel
                  </button>
                </span>
              ) : null,
            width: "160px",
          } satisfies DataGridColumn<PlannedOrder>,
        ]
      : []),
  ];

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/manufacturing/mrp/runs">MRP Runs</Link> /{" "}
          <span className="text-ink">{data.run_number}</span>
        </p>
        <div className="mt-1.5 flex items-center gap-3">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.run_number}</h1>
          <StatusPill status={data.status} />
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Run date</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.run_date}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Horizon</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.horizon_days} days</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Planned MAKE</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{data.planned_make_count}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Planned BUY</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{data.planned_buy_count}</dd>
        </div>
      </dl>

      {data.capacity_loads.length > 0 && (
        <div className="mt-8 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
          <h2 className="mono-caps mb-3.5 text-ink-muted">Rough capacity check</h2>
          <table className="mt-2 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left mono-caps text-ink-muted">
                <th className="py-1.5 pr-2">Work center</th>
                <th className="py-1.5 pr-2 text-right">Load (min)</th>
                <th className="py-1.5 pr-2 text-right">Available (min)</th>
                <th className="py-1.5 pr-2 text-right">Utilization</th>
              </tr>
            </thead>
            <tbody>
              {data.capacity_loads.map((load) => (
                <tr key={load.id} className="border-b border-line last:border-b-0">
                  <td className="py-1.5 pr-2 text-ink">{workCenterLabel(load.work_center_id)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(load.planned_load_minutes)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(load.available_minutes)}</td>
                  <td className={`py-1.5 pr-2 text-right tabular-nums ${load.is_overloaded ? "font-semibold text-danger" : ""}`}>
                    {formatPercent(load.utilization_percent)}{load.is_overloaded ? " (overloaded)" : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-8 flex items-center justify-between">
        <h2 className="mono-caps text-ink-muted">Planned orders</h2>
        <div className="flex gap-2">
          {canManagePlanned && needsConvertWarehouse && (
            <select
              value={convertWarehouseId}
              onChange={(event) => setConvertWarehouseId(event.target.value)}
              aria-label="Warehouse for MAKE converts"
              className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Convert warehouse…</option>
              {(warehouses.data?.items ?? []).map((warehouse) => (
                <option key={warehouse.id} value={warehouse.id}>
                  {warehouse.code} — {warehouse.name}
                </option>
              ))}
            </select>
          )}
          <select
            value={orderType}
            onChange={(event) => setOrderType(event.target.value as PlannedOrderType | "")}
            className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">All types</option>
            <option value="MAKE">Make</option>
            <option value="BUY">Buy</option>
          </select>
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as PlannedOrderStatus | "")}
            className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">All statuses</option>
            <option value="PLANNED">Planned</option>
            <option value="FIRMED">Firmed</option>
            <option value="CONVERTED">Converted</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      <div className="mt-2">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={plannedOrders.isPending}
          emptyMessage="No planned orders in this run."
          isFiltered={Boolean(orderType || status)}
          onClearFilters={() => {
            setOrderType("");
            setStatus("");
          }}
          hasMore={plannedOrders.hasNextPage}
          onLoadMore={() => void plannedOrders.fetchNextPage()}
          loadingMore={plannedOrders.isFetchingNextPage}
          label="Planned orders"
        />
      </div>
    </div>
  );
}
