/**
 * The inspection-lot workbench (STRUCTURE §4): view the lot header, then — while OPEN — record
 * the usage decision (split the lot quantity into accepted/rejected; a rejection requires a
 * SCRAP or BLOCK disposition, and BLOCK requires the destination quarantine bin) or cancel the
 * lot. A decided lot is terminal; the accepted stock is already on hand (v1 lots never hold
 * stock aside), so an ACCEPT moves nothing — only a REJECT dispositions stock.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { StatusPill } from "@/components/StatusPill";
import { useBinLookup, useBinOptions, useItemLookup, useWarehouseLookup } from "@/modules/inventory/hooks";
import { useCancelInspectionLot, useDecideInspectionLot, useInspectionLot } from "@/modules/quality/hooks";
import type { InspectionLot } from "@/modules/quality/types";

function DecisionPanel({ lot }: { lot: InspectionLot }) {
  const decideLot = useDecideInspectionLot(lot.id);
  const bins = useBinOptions(lot.warehouse_id);

  const [acceptedQuantity, setAcceptedQuantity] = useState(lot.quantity);
  const [rejectedQuantity, setRejectedQuantity] = useState("0");
  const [disposition, setDisposition] = useState<"SCRAP" | "BLOCK" | "">("");
  const [blockedBinId, setBlockedBinId] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rejecting = Number(rejectedQuantity) > 0;
  const submittable =
    acceptedQuantity !== "" &&
    rejectedQuantity !== "" &&
    (!rejecting || (disposition !== "" && (disposition !== "BLOCK" || blockedBinId !== "")));

  const decide = async () => {
    setError(null);
    try {
      await decideLot.mutateAsync({
        accepted_quantity: acceptedQuantity,
        rejected_quantity: rejectedQuantity,
        disposition: rejecting ? disposition || null : null,
        blocked_bin_id: rejecting && disposition === "BLOCK" ? blockedBinId : null,
        notes: notes || null,
      });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to record the usage decision."));
    }
  };

  const control = "w-full rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink";

  return (
    <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
      <h2 className="mono-caps mb-3.5 text-ink-muted">Usage decision</h2>
      <p className="text-[12px] text-ink-muted">
        Accepted plus rejected must equal the lot quantity ({formatQuantity(lot.quantity)}). Accepted
        stock stays where it is; rejected stock is scrapped (written off) or blocked (moved to a
        quarantine bin).
      </p>
      {error && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="accepted-quantity" className="mb-1 block text-xs font-medium text-ink-muted">
            Accepted quantity
          </label>
          <input
            id="accepted-quantity"
            type="number"
            min="0"
            step="0.000001"
            value={acceptedQuantity}
            onChange={(event) => setAcceptedQuantity(event.target.value)}
            className={control}
          />
        </div>
        <div>
          <label htmlFor="rejected-quantity" className="mb-1 block text-xs font-medium text-ink-muted">
            Rejected quantity
          </label>
          <input
            id="rejected-quantity"
            type="number"
            min="0"
            step="0.000001"
            value={rejectedQuantity}
            onChange={(event) => setRejectedQuantity(event.target.value)}
            className={control}
          />
        </div>
        {rejecting && (
          <div>
            <label htmlFor="disposition" className="mb-1 block text-xs font-medium text-ink-muted">
              Disposition
            </label>
            <select
              id="disposition"
              value={disposition}
              onChange={(event) => setDisposition(event.target.value as "SCRAP" | "BLOCK" | "")}
              className={control}
            >
              <option value="">Select disposition</option>
              <option value="SCRAP">Scrap — write the stock off</option>
              <option value="BLOCK">Block — move to a quarantine bin</option>
            </select>
          </div>
        )}
        {rejecting && disposition === "BLOCK" && (
          <div>
            <label htmlFor="blocked-bin" className="mb-1 block text-xs font-medium text-ink-muted">
              Blocked bin
            </label>
            <select
              id="blocked-bin"
              value={blockedBinId}
              onChange={(event) => setBlockedBinId(event.target.value)}
              className={control}
            >
              <option value="">Select bin</option>
              {(bins.data?.items ?? []).map((bin) => (
                <option key={bin.id} value={bin.id}>
                  {bin.code} — {bin.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="col-span-2">
          <label htmlFor="decision-notes" className="mb-1 block text-xs font-medium text-ink-muted">
            Notes (optional)
          </label>
          <textarea
            id="decision-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className={control}
          />
        </div>
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => void decide()}
          disabled={!submittable || decideLot.isPending}
          className="btn-ink"
        >
          {decideLot.isPending ? "Recording…" : "Record decision"}
        </button>
      </div>
    </div>
  );
}

export function InspectionLotDetailPage() {
  const { lotId } = useParams({ strict: false });
  const me = useMe();
  const canDecide = (me.data?.permissions ?? []).includes("quality.inspection.decide");
  const canManage = (me.data?.permissions ?? []).includes("quality.inspection.manage");

  const lot = useInspectionLot(lotId);
  const items = useItemLookup();
  const warehouses = useWarehouseLookup();
  const binLookup = useBinLookup();
  const cancelLot = useCancelInspectionLot(lotId ?? "");
  const [error, setError] = useState<string | null>(null);

  if (lot.isPending || !lot.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = lot.data;
  const isOpen = data.status === "OPEN";

  const item = items.data?.items.find((i) => i.id === data.item_id);
  const warehouse = warehouses.data?.items.find((w) => w.id === data.warehouse_id);
  const bin = binLookup.data?.items.find((b) => b.id === data.bin_id);

  const cancel = async () => {
    setError(null);
    try {
      await cancelLot.mutateAsync();
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to cancel the inspection lot."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/quality/inspection-lots">Inspection lots</Link> /{" "}
          <span className="text-ink">{data.lot_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.lot_number}</h1>
          <div className="flex items-center gap-2.5">
            {isOpen && canManage && (
              <button
                type="button"
                onClick={() => void cancel()}
                disabled={cancelLot.isPending}
                className="btn-chip hover:border-danger hover:text-danger"
              >
                Cancel lot
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

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Status</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            <StatusPill status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Item</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{item ? `${item.item_code} — ${item.name}` : data.item_id}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Quantity</dt>
          <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{formatQuantity(data.quantity)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Warehouse</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {warehouse ? `${warehouse.code} — ${warehouse.name}` : data.warehouse_id}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Bin</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{bin ? `${bin.code} — ${bin.name}` : data.bin_id}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Created</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{formatDate(data.created_date)}</dd>
        </div>
        {data.status !== "OPEN" && data.status !== "CANCELLED" && (
          <>
            <div>
              <dt className="mono-caps text-ink-muted">Accepted</dt>
              <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{formatQuantity(data.accepted_quantity)}</dd>
            </div>
            <div>
              <dt className="mono-caps text-ink-muted">Rejected</dt>
              <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{formatQuantity(data.rejected_quantity)}</dd>
            </div>
            <div>
              <dt className="mono-caps text-ink-muted">Disposition</dt>
              <dd className="mt-1.5 text-[13px] text-ink">{data.disposition ?? "—"}</dd>
            </div>
            <div>
              <dt className="mono-caps text-ink-muted">Decided</dt>
              <dd className="mt-1.5 text-[13px] text-ink">
                {data.decided_date ? formatDate(data.decided_date) : "—"}
              </dd>
            </div>
          </>
        )}
        <div>
          <dt className="mono-caps text-ink-muted">Notes</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.notes ?? "—"}</dd>
        </div>
      </dl>

      {isOpen && canDecide && <DecisionPanel lot={data} />}
    </div>
  );
}
