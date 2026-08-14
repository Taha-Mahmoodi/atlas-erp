/**
 * Create a stock count (STRUCTURE §4). PHYSICAL counts snapshot the whole warehouse;
 * CYCLE counts narrow to chosen items and/or bins — `item_ids`/`bin_ids` are ignored
 * server-side for PHYSICAL, so this form only shows them once CYCLE is selected.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useBinOptions, useCreateStockCount, useItemOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import type { CountType } from "@/modules/inventory/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function StockCountFormPage() {
  const navigate = useNavigate();
  const warehouses = useWarehouseOptions();
  const items = useItemOptions();
  const createCount = useCreateStockCount();

  const [countType, setCountType] = useState<CountType>("PHYSICAL");
  const [warehouseId, setWarehouseId] = useState("");
  const [countDate, setCountDate] = useState(today());
  const [description, setDescription] = useState("");
  const [itemIds, setItemIds] = useState<string[]>([]);
  const bins = useBinOptions(warehouseId || undefined);
  const [binIds, setBinIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = Boolean(warehouseId);

  const submit = async () => {
    setError(null);
    try {
      const created = await createCount.mutateAsync({
        count_type: countType,
        warehouse_id: warehouseId,
        count_date: countDate,
        description: description || null,
        ...(countType === "CYCLE" && itemIds.length > 0 ? { item_ids: itemIds } : {}),
        ...(countType === "CYCLE" && binIds.length > 0 ? { bin_ids: binIds } : {}),
      });
      void navigate({ to: "/inventory/stock-counts/$countId", params: { countId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the stock count."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory/stock-counts">Stock Counts</Link> / <span className="text-ink">New stock count</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New stock count</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Count type</label>
          <select
            value={countType}
            onChange={(event) => {
              setCountType(event.target.value as CountType);
              setItemIds([]);
              setBinIds([]);
            }}
            className={CONTROL}
          >
            <option value="PHYSICAL">Physical (whole warehouse)</option>
            <option value="CYCLE">Cycle (chosen items/bins)</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Warehouse</label>
          <select value={warehouseId} onChange={(event) => setWarehouseId(event.target.value)} className={CONTROL}>
            <option value="">Select warehouse</option>
            {(warehouses.data?.items ?? []).map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.code} — {warehouse.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Count date</label>
          <input type="date" value={countDate} onChange={(event) => setCountDate(event.target.value)} className={CONTROL} />
        </div>
        <div className="col-span-2">
          <label className="mb-1 block text-xs font-medium text-ink-muted">Description</label>
          <input type="text" value={description} onChange={(event) => setDescription(event.target.value)} className={CONTROL} />
        </div>
      </div>

      {countType === "CYCLE" && (
        <div className="mt-6 grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Items (optional — leave empty for all)</label>
            <select
              multiple
              value={itemIds}
              onChange={(event) => setItemIds(Array.from(event.target.selectedOptions, (option) => option.value))}
              className={`${CONTROL} h-40`}
            >
              {(items.data?.items ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.item_code} — {item.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Bins (optional — leave empty for all)</label>
            <select
              multiple
              value={binIds}
              onChange={(event) => setBinIds(Array.from(event.target.selectedOptions, (option) => option.value))}
              disabled={!warehouseId}
              className={`${CONTROL} h-40`}
            >
              {(bins.data?.items ?? []).map((bin) => (
                <option key={bin.id} value={bin.id}>
                  {bin.code} — {bin.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createCount.isPending}
        className="mt-6 btn-ink"
      >
        {createCount.isPending ? "Creating…" : "Create count"}
      </button>
    </div>
  );
}
