/**
 * The stock count workbench (STRUCTURE §4): record counted quantities per line, preview the
 * variance before committing, then post or cancel. Posting re-reads LIVE on-hand per line (not
 * the line's own possibly-stale snapshot) and posts one ADJUSTMENT move per non-zero variance
 * through the normal costing/event-bus pipeline — finance posts the GL journal in the same
 * transaction, so there's no separate "count journal" to show here. Small counts post inline
 * (200); larger ones return a job to poll (202, PERFORMANCE §3), mirroring the bank-import/
 * depreciation-run pattern.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { pollJob } from "@/lib/jobs";
import { formatMoney, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import {
  useBinLookup,
  useCancelStockCount,
  useItemLookup,
  usePostStockCount,
  useRecordCountedQuantity,
  useStockCount,
  useStockCountLines,
  useStockCountVariancePreview,
  useWarehouseLookup,
} from "@/modules/inventory/hooks";

export function StockCountDetailPage() {
  const { countId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.count.manage");
  const canPost = (me.data?.permissions ?? []).includes("inventory.count.post");

  const count = useStockCount(countId);
  const lines = useStockCountLines(countId);
  const items = useItemLookup();
  const bins = useBinLookup();
  const warehouses = useWarehouseLookup();
  const recordCount = useRecordCountedQuantity(countId ?? "");
  const postCount = usePostStockCount();
  const cancelCount = useCancelStockCount(countId ?? "");
  const currency = useFunctionalCurrency();
  const currencyCode = currency.data ?? "—";

  const [countedInputs, setCountedInputs] = useState<Record<string, string>>({});
  const [showPreview, setShowPreview] = useState(false);
  const preview = useStockCountVariancePreview(countId ?? "", showPreview);
  const [error, setError] = useState<string | null>(null);
  const [awaitingJob, setAwaitingJob] = useState(false);

  if (count.isPending || !count.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = count.data;
  const isEditable = data.status === "DRAFT" || data.status === "COUNTING";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };
  const binLabel = (id: string) => {
    const bin = bins.data?.items.find((b) => b.id === id);
    return bin ? `${bin.code} — ${bin.name}` : id;
  };
  const warehouseLabel = (id: string) => {
    const warehouse = warehouses.data?.items.find((w) => w.id === id);
    return warehouse ? `${warehouse.code} — ${warehouse.name}` : id;
  };

  const saveCount = async (lineId: string) => {
    setError(null);
    const counted = countedInputs[lineId];
    if (!counted) return;
    try {
      await recordCount.mutateAsync({ lineId, payload: { counted_qty: counted } });
      setCountedInputs((prev) => {
        const next = { ...prev };
        delete next[lineId];
        return next;
      });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to record the counted quantity."));
    }
  };

  const post = async () => {
    setError(null);
    try {
      const result = await postCount.mutateAsync(data.id);
      if ("job_id" in result) {
        setAwaitingJob(true);
        const job = await pollJob(result.job_id);
        setAwaitingJob(false);
        if (job.status === "FAILED") {
          setError(job.error ?? "Post failed.");
          return;
        }
      }
      void count.refetch();
      void lines.refetch();
    } catch (caught) {
      setAwaitingJob(false);
      setError(getErrorMessage(caught, "Unable to post the count."));
    }
  };

  const cancel = async () => {
    setError(null);
    try {
      await cancelCount.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the count."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.count_number}</h1>
        {isEditable && (
          <div className="flex gap-2">
            {canManage && (
              <button
                type="button"
                onClick={() => setShowPreview(true)}
                className="btn-chip"
              >
                Preview variance
              </button>
            )}
            {canManage && (
              <button
                type="button"
                onClick={() => void cancel()}
                disabled={cancelCount.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Cancel
              </button>
            )}
            {canPost && (
              <button
                type="button"
                onClick={() => void post()}
                disabled={postCount.isPending || awaitingJob}
                className="btn-ink"
              >
                {awaitingJob ? "Processing large count…" : postCount.isPending ? "Posting…" : "Post"}
              </button>
            )}
          </div>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Type</dt>
          <dd className="text-ink">{data.count_type}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Warehouse</dt>
          <dd className="text-ink">{warehouseLabel(data.warehouse_id)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Description</dt>
          <dd className="text-ink">{data.description ?? "—"}</dd>
        </div>
      </dl>

      {showPreview && (
        <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
          <h2 className="text-sm font-semibold text-ink">Variance preview</h2>
          {preview.isPending ? (
            <p className="mt-2 text-sm text-ink-muted">Loading…</p>
          ) : (
            <>
              <div className="mt-2 flex items-center justify-between text-sm">
                <span className="text-ink-muted">Total estimated value impact</span>
                <span className="tabular-nums font-medium text-ink">
                  {formatMoney(preview.data?.total_value_impact ?? "0", currencyCode)}
                </span>
              </div>
              <table className="mt-3 w-full border-collapse text-[13px]">
                <thead>
                  <tr className="border-b border-line text-left mono-caps text-ink-muted">
                    <th className="py-1.5 pr-2">Item</th>
                    <th className="py-1.5 pr-2">Bin</th>
                    <th className="py-1.5 pr-2 text-right">System</th>
                    <th className="py-1.5 pr-2 text-right">Counted</th>
                    <th className="py-1.5 pr-2 text-right">Variance</th>
                    <th className="py-1.5 pr-2 text-right">Value impact</th>
                  </tr>
                </thead>
                <tbody>
                  {(preview.data?.lines.items ?? []).map((line) => (
                    <tr key={line.line_id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
                      <td className="py-1.5 pr-2 text-ink-muted">{binLabel(line.bin_id)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.system_qty)}</td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {line.counted_qty ? formatQuantity(line.counted_qty) : "—"}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {line.variance_qty ? formatQuantity(line.variance_qty) : "—"}
                      </td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">
                        {formatMoney(line.estimated_value_impact, currencyCode)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Item</th>
            <th className="py-2 pr-2">Bin</th>
            <th className="py-2 pr-2 text-right">System qty</th>
            <th className="py-2 pr-2 text-right">Counted qty</th>
            <th className="py-2 pr-2 text-right">Variance</th>
            {isEditable && canManage && <th className="py-2 pr-2">Action</th>}
          </tr>
        </thead>
        <tbody>
          {(lines.data?.items ?? []).map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{binLabel(line.bin_id)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.system_qty)}</td>
              <td className="py-1.5 pr-2 text-right">
                {isEditable && canManage ? (
                  <input
                    type="number"
                    step="0.000001"
                    value={countedInputs[line.id] ?? line.counted_qty ?? ""}
                    onChange={(event) =>
                      setCountedInputs((prev) => ({ ...prev, [line.id]: event.target.value }))
                    }
                    className="w-28 rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                  />
                ) : (
                  <span className="tabular-nums">{line.counted_qty ? formatQuantity(line.counted_qty) : "—"}</span>
                )}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">
                {line.variance_qty ? formatQuantity(line.variance_qty) : "—"}
              </td>
              {isEditable && canManage && (
                <td className="py-1.5 pr-2">
                  <button
                    type="button"
                    onClick={() => void saveCount(line.id)}
                    disabled={!countedInputs[line.id] || recordCount.isPending}
                    className="text-xs font-medium text-primary hover:underline disabled:opacity-45"
                  >
                    Save
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
