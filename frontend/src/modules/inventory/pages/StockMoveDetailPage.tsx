/**
 * Stock move detail (STRUCTURE §4): view + Reverse. A move can only be reversed once (a
 * second attempt 409s server-side) — this UI doesn't try to detect that ahead of time, it
 * just surfaces whatever error the backend returns.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useItemLookup, useReverseStockMove, useStockMove } from "@/modules/inventory/hooks";

export function StockMoveDetailPage() {
  const { moveId } = useParams({ strict: false });
  const me = useMe();
  const canCreate = (me.data?.permissions ?? []).includes("inventory.move.create");
  const move = useStockMove(moveId);
  const items = useItemLookup();
  const reverseMove = useReverseStockMove();
  const [error, setError] = useState<string | null>(null);
  const [reversedInto, setReversedInto] = useState<string | null>(null);

  if (move.isPending || !move.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = move.data;
  const item = items.data?.items.find((i) => i.id === data.item_id);

  const reverse = async () => {
    setError(null);
    try {
      const reversal = await reverseMove.mutateAsync(data.id);
      setReversedInto(reversal.move_number);
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to reverse the move."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.move_number}</h1>
        {canCreate && (
          <button
            type="button"
            onClick={() => void reverse()}
            disabled={reverseMove.isPending || reversedInto !== null}
            className="btn-chip hover:border-danger hover:text-danger"
          >
            {reverseMove.isPending ? "Reversing…" : "Reverse"}
          </button>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {reversedInto && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Reversed by {reversedInto}.
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Type</dt>
          <dd className="text-ink">{data.move_type}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Item</dt>
          <dd className="text-ink">{item ? `${item.item_code} — ${item.name}` : data.item_id}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Quantity</dt>
          <dd className="tabular-nums text-ink">{formatQuantity(data.quantity)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Move date</dt>
          <dd className="text-ink">{formatDate(data.move_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Reference</dt>
          <dd className="text-ink">{data.reference ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Unit cost</dt>
          <dd className="tabular-nums text-ink">{data.unit_cost ?? "—"}</dd>
        </div>
      </dl>
    </div>
  );
}
