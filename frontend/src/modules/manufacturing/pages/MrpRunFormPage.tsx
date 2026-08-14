/**
 * Trigger an MRP run (STRUCTURE §4). The submit is ALWAYS a 202 background job (D-049) — this
 * page polls it via lib/jobs and navigates to the finished run, the DepreciationRunFormPage
 * job-polling pattern. Warehouse scope is optional: unscoped runs net demand across all
 * warehouses (MAKE converts then ask for a warehouse at convert time).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { pollJob } from "@/lib/jobs";
import { useWarehouseOptions } from "@/modules/inventory/hooks";
import { useRunMrp } from "@/modules/manufacturing/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function MrpRunFormPage() {
  const navigate = useNavigate();
  const warehouses = useWarehouseOptions();
  const runMrp = useRunMrp();

  const [runDate, setRunDate] = useState(today());
  const [horizonDays, setHorizonDays] = useState("30");
  const [warehouseId, setWarehouseId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [awaitingJob, setAwaitingJob] = useState(false);

  const submit = async () => {
    setError(null);
    try {
      const submitted = await runMrp.mutateAsync({
        run_date: runDate || null,
        horizon_days: horizonDays ? Number(horizonDays) : null,
        warehouse_id: warehouseId || null,
      });
      setAwaitingJob(true);
      const job = await pollJob<{ run_id: string }>(submitted.job_id);
      setAwaitingJob(false);
      if (job.status === "FAILED") {
        setError(job.error ?? "MRP run failed.");
        return;
      }
      const runId = job.result?.run_id;
      if (runId) {
        void navigate({ to: "/manufacturing/mrp/runs/$runId", params: { runId } });
      }
    } catch (caught) {
      setAwaitingJob(false);
      setError(getErrorMessage(caught, "Unable to run MRP."));
    }
  };

  return (
    <div className="mx-auto max-w-xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/manufacturing/mrp/runs">MRP Runs</Link> /{" "}
          <span className="text-ink">Run MRP</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Run MRP</h1>
        <p className="mt-1 text-[13px] text-ink-muted">
          Explodes sales demand and reorder points against supply into planned MAKE/BUY orders, plus a
          rough capacity check per work center.
        </p>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="run-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Run date
          </label>
          <input
            id="run-date"
            type="date"
            value={runDate}
            onChange={(event) => setRunDate(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label htmlFor="horizon-days" className="mb-1 block text-xs font-medium text-ink-muted">
            Horizon (days)
          </label>
          <input
            id="horizon-days"
            type="number"
            min="1"
            step="1"
            value={horizonDays}
            onChange={(event) => setHorizonDays(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </div>
        <div className="col-span-2">
          <label htmlFor="warehouse" className="mb-1 block text-xs font-medium text-ink-muted">
            Warehouse (optional — all when unset)
          </label>
          <select
            id="warehouse"
            value={warehouseId}
            onChange={(event) => setWarehouseId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="">All warehouses</option>
            {(warehouses.data?.items ?? []).map((warehouse) => (
              <option key={warehouse.id} value={warehouse.id}>
                {warehouse.code} — {warehouse.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!runDate || runMrp.isPending || awaitingJob}
        className="mt-6 btn-ink"
      >
        {awaitingJob ? "Running…" : runMrp.isPending ? "Submitting…" : "Run MRP"}
      </button>
    </div>
  );
}
