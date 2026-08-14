/**
 * Stock valuation (STRUCTURE §4). `StockValuationRead` (moving-average state) and
 * `CostLayerRead` (FIFO layers) are both read-only projections per (item, warehouse) — not
 * per bin, since valuation isn't bin-scoped. Only one is meaningful per item depending on its
 * costing_method, so this page offers both: a valuations table (moving-average items) and a
 * cost-layer lookup tool (FIFO items, pick item + warehouse to see its layers oldest-first).
 */

import { useState } from "react";

import { formatMoney, formatQuantity } from "@/lib/format";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import {
  useCostLayers,
  useItemLookup,
  useItemOptions,
  useStockValuations,
  useWarehouseLookup,
  useWarehouseOptions,
} from "@/modules/inventory/hooks";
import type { StockValuation } from "@/modules/inventory/types";

export function StockValuationPage() {
  const [itemId, setItemId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const items = useItemOptions();
  const warehouses = useWarehouseOptions();
  const itemLookup = useItemLookup();
  const warehouseLookup = useWarehouseLookup();
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  const valuations = useStockValuations({
    ...(itemId ? { item_id: itemId } : {}),
    ...(warehouseId ? { warehouse_id: warehouseId } : {}),
  });
  const rows = valuations.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (id: string) => {
    const item = itemLookup.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouseLookup.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const columns: DataGridColumn<StockValuation>[] = [
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    { key: "warehouse_id", header: "Warehouse", render: (row) => warehouseLabel(row.warehouse_id) },
    { key: "on_hand_qty", header: "On hand", align: "right", render: (row) => formatQuantity(row.on_hand_qty), width: "110px" },
    { key: "avg_unit_cost", header: "Avg unit cost", align: "right", render: (row) => formatMoney(row.avg_unit_cost, currencyCode), width: "130px" },
    { key: "total_value", header: "Total value", align: "right", render: (row) => formatMoney(row.total_value, currencyCode), width: "130px" },
  ];

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Stock Valuation</h1>

      <div className="mt-4 flex gap-4">
        <select
          value={itemId}
          onChange={(event) => setItemId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All items</option>
          {(items.data?.items ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.item_code} — {item.name}
            </option>
          ))}
        </select>
        <select
          value={warehouseId}
          onChange={(event) => setWarehouseId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All warehouses</option>
          {(warehouses.data?.items ?? []).map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.code} — {warehouse.name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => `${row.item_id}:${row.warehouse_id}`}
          loading={valuations.isPending}
          emptyMessage="No moving-average valuation for this filter — FIFO items are valued via cost layers below instead."
          hasMore={valuations.hasNextPage}
          onLoadMore={() => void valuations.fetchNextPage()}
          loadingMore={valuations.isFetchingNextPage}
          label="Stock valuations"
        />
      </div>

      <CostLayersLookup />
    </div>
  );
}

function CostLayersLookup() {
  const items = useItemOptions();
  const warehouses = useWarehouseOptions();
  const [itemId, setItemId] = useState("");
  const [warehouseId, setWarehouseId] = useState("");
  const layers = useCostLayers(itemId || undefined, warehouseId || undefined);
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  return (
    <div className="mt-8 rounded-card border border-line bg-surface p-4 shadow-card">
      <h2 className="text-sm font-semibold text-ink">FIFO cost layers</h2>
      <p className="mt-1 text-xs text-ink-muted">Oldest-first; layers are consumed in this order as stock issues.</p>

      <div className="mt-3 flex gap-4">
        <select
          value={itemId}
          onChange={(event) => setItemId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">Select item</option>
          {(items.data?.items ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.item_code} — {item.name}
            </option>
          ))}
        </select>
        <select
          value={warehouseId}
          onChange={(event) => setWarehouseId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">Select warehouse</option>
          {(warehouses.data?.items ?? []).map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.code} — {warehouse.name}
            </option>
          ))}
        </select>
      </div>

      {itemId && warehouseId && (
        <table className="mt-3 w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
              <th className="py-1.5 pr-2">Received</th>
              <th className="py-1.5 pr-2 text-right">Original qty</th>
              <th className="py-1.5 pr-2 text-right">Remaining qty</th>
              <th className="py-1.5 pr-2 text-right">Unit cost</th>
            </tr>
          </thead>
          <tbody>
            {layers.isPending ? (
              <tr>
                <td colSpan={4} className="py-4 text-center text-sm text-ink-muted">Loading…</td>
              </tr>
            ) : (layers.data?.items ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="py-4 text-center text-sm text-ink-muted">No cost layers.</td>
              </tr>
            ) : (
              layers.data?.items.map((layer) => (
                <tr key={layer.id} className="border-b border-line last:border-b-0">
                  <td className="py-1.5 pr-2 text-ink-muted">{layer.received_at}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-ink">{formatQuantity(layer.original_qty)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-ink">{formatQuantity(layer.remaining_qty)}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-ink">{formatMoney(layer.unit_cost, currencyCode)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
