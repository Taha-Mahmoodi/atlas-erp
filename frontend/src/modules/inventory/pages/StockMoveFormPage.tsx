/**
 * Create a stock move (STRUCTURE §4). Moves are immutable and posted at creation — no draft
 * state — so this is create-only; corrections happen via the detail page's Reverse action.
 * Which bin side(s) are shown depends on move_type (server-enforced, mirrored here):
 * RECEIPT needs only `to_bin_id`, ISSUE only `from_bin_id`, TRANSFER both (and they must
 * differ), ADJUSTMENT exactly one — this form models that as a direction toggle rather than
 * exposing both bin pickers for an adjustment.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useBinOptions, useCreateStockMove, useItemOptions, useWarehouseOptions } from "@/modules/inventory/hooks";
import type { MoveType, StockMoveCreate } from "@/modules/inventory/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function BinPicker({
  label,
  warehouseId,
  onWarehouseChange,
  binId,
  onBinChange,
}: {
  label: string;
  warehouseId: string;
  onWarehouseChange: (id: string) => void;
  binId: string;
  onBinChange: (id: string) => void;
}) {
  const warehouses = useWarehouseOptions();
  const bins = useBinOptions(warehouseId || undefined);

  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <label className="mb-1 block text-xs font-medium text-ink-muted">{label} warehouse</label>
        <select
          value={warehouseId}
          onChange={(event) => {
            onWarehouseChange(event.target.value);
            onBinChange("");
          }}
          className={CONTROL}
        >
          <option value="">Select warehouse</option>
          {(warehouses.data?.items ?? []).map((warehouse) => (
            <option key={warehouse.id} value={warehouse.id}>
              {warehouse.code} — {warehouse.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-xs font-medium text-ink-muted">{label} bin</label>
        <select value={binId} onChange={(event) => onBinChange(event.target.value)} className={CONTROL}>
          <option value="">Select bin</option>
          {(bins.data?.items ?? []).map((bin) => (
            <option key={bin.id} value={bin.id}>
              {bin.code} — {bin.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export function StockMoveFormPage() {
  const navigate = useNavigate();
  const items = useItemOptions();
  const createMove = useCreateStockMove();

  const [moveType, setMoveType] = useState<MoveType>("RECEIPT");
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("");
  const [moveDate, setMoveDate] = useState(today());
  const [reference, setReference] = useState("");
  const [unitCost, setUnitCost] = useState("");
  const [direction, setDirection] = useState<"INCREASE" | "DECREASE">("INCREASE");
  const [fromWarehouseId, setFromWarehouseId] = useState("");
  const [fromBinId, setFromBinId] = useState("");
  const [toWarehouseId, setToWarehouseId] = useState("");
  const [toBinId, setToBinId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const needsFrom = moveType === "ISSUE" || moveType === "TRANSFER" || (moveType === "ADJUSTMENT" && direction === "DECREASE");
  const needsTo = moveType === "RECEIPT" || moveType === "TRANSFER" || (moveType === "ADJUSTMENT" && direction === "INCREASE");
  const needsUnitCost = moveType === "RECEIPT" || (moveType === "ADJUSTMENT" && direction === "INCREASE");

  const canSubmit =
    Boolean(itemId && Number(quantity) > 0) &&
    (!needsFrom || Boolean(fromBinId)) &&
    (!needsTo || Boolean(toBinId)) &&
    (!needsUnitCost || Boolean(unitCost));

  const submit = async () => {
    setError(null);
    try {
      const payload: StockMoveCreate = {
        move_type: moveType,
        item_id: itemId,
        quantity,
        move_date: moveDate,
        reference: reference || null,
        ...(needsFrom ? { from_bin_id: fromBinId } : {}),
        ...(needsTo ? { to_bin_id: toBinId } : {}),
        ...(needsUnitCost ? { unit_cost: unitCost } : {}),
      };
      const move = await createMove.mutateAsync(payload);
      void navigate({ to: "/inventory/stock-moves/$moveId", params: { moveId: move.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the stock move."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-xl font-semibold text-ink">New stock move</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Move type</label>
          <select
            value={moveType}
            onChange={(event) => {
              setMoveType(event.target.value as MoveType);
              setFromBinId("");
              setToBinId("");
            }}
            className={CONTROL}
          >
            <option value="RECEIPT">Receipt</option>
            <option value="ISSUE">Issue</option>
            <option value="TRANSFER">Transfer</option>
            <option value="ADJUSTMENT">Adjustment</option>
          </select>
        </div>
        {moveType === "ADJUSTMENT" && (
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Direction</label>
            <select
              value={direction}
              onChange={(event) => setDirection(event.target.value as "INCREASE" | "DECREASE")}
              className={CONTROL}
            >
              <option value="INCREASE">Increase</option>
              <option value="DECREASE">Decrease</option>
            </select>
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Item</label>
          <select value={itemId} onChange={(event) => setItemId(event.target.value)} className={CONTROL}>
            <option value="">Select item</option>
            {(items.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.item_code} — {item.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Quantity (base UoM)</label>
          <input
            type="number"
            step="0.000001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Move date</label>
          <input type="date" value={moveDate} onChange={(event) => setMoveDate(event.target.value)} className={CONTROL} />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-ink-muted">Reference</label>
          <input type="text" value={reference} onChange={(event) => setReference(event.target.value)} className={CONTROL} />
        </div>
        {needsUnitCost && (
          <div>
            <label className="mb-1 block text-xs font-medium text-ink-muted">Unit cost</label>
            <input
              type="number"
              step="0.000001"
              value={unitCost}
              onChange={(event) => setUnitCost(event.target.value)}
              className={CONTROL}
            />
          </div>
        )}
      </div>

      {needsFrom && (
        <div className="mt-6">
          <BinPicker
            label="From"
            warehouseId={fromWarehouseId}
            onWarehouseChange={setFromWarehouseId}
            binId={fromBinId}
            onBinChange={setFromBinId}
          />
        </div>
      )}
      {needsTo && (
        <div className="mt-6">
          <BinPicker
            label="To"
            warehouseId={toWarehouseId}
            onWarehouseChange={setToWarehouseId}
            binId={toBinId}
            onBinChange={setToBinId}
          />
        </div>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createMove.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createMove.isPending ? "Creating…" : "Create move"}
      </button>
    </div>
  );
}
