/**
 * Stock move detail (STRUCTURE §4): view + Reverse. A move can only be reversed once (a
 * second attempt 409s server-side) — this UI doesn't try to detect that ahead of time, it
 * just surfaces whatever error the backend returns.
 */

import { Link, useParams } from "@tanstack/react-router";
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
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
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
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/inventory/stock-moves">Stock Moves</Link> /{" "}
          <span className="text-ink">{data.move_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.move_number}</h1>
          <div className="flex items-center gap-2.5">
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
        </div>
      </header>

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

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
        <div>
          <dt className="mono-caps text-ink-muted">Type</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.move_type}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Item</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{item ? `${item.item_code} — ${item.name}` : data.item_id}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Quantity</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums text-ink">{formatQuantity(data.quantity)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Move date</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{formatDate(data.move_date)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Reference</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.reference ?? "—"}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Unit cost</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums text-ink">{data.unit_cost ?? "—"}</dd>
        </div>
      </dl>
    </div>
  );
}
