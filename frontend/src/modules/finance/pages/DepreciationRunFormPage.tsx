/**
 * Run depreciation for a fiscal period (STRUCTURE §4). Small periods (<= 100 eligible assets)
 * return the finished run inline (201); larger ones return a job to poll (202, PERFORMANCE
 * §3) — mirrors BankStatementImportPage's handling of the same union-response pattern.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { pollJob } from "@/lib/jobs";
import { useFiscalPeriods, useRunDepreciation } from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function DepreciationRunFormPage() {
  const navigate = useNavigate();
  const fiscalPeriods = useFiscalPeriods();
  const runDepreciation = useRunDepreciation();

  const [fiscalPeriodId, setFiscalPeriodId] = useState("");
  const [runDate, setRunDate] = useState(today());
  const [error, setError] = useState<string | null>(null);
  const [awaitingJob, setAwaitingJob] = useState(false);

  const canSubmit = Boolean(fiscalPeriodId && runDate);

  const submit = async () => {
    setError(null);
    try {
      const result = await runDepreciation.mutateAsync({
        fiscal_period_id: fiscalPeriodId,
        run_date: runDate,
      });

      if ("job_id" in result) {
        setAwaitingJob(true);
        const job = await pollJob<{ run_id: string }>(result.job_id);
        setAwaitingJob(false);
        if (job.status === "FAILED") {
          setError(job.error ?? "Depreciation run failed.");
          return;
        }
        const runId = job.result?.run_id;
        if (runId) {
          void navigate({ to: "/finance/depreciation-runs/$runId", params: { runId } });
        }
        return;
      }

      void navigate({ to: "/finance/depreciation-runs/$runId", params: { runId: result.id } });
    } catch (caught) {
      setAwaitingJob(false);
      setError(getErrorMessage(caught, "Unable to run depreciation."));
    }
  };

  return (
    <div className="mx-auto max-w-xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/depreciation-runs">Depreciation Runs</Link> /{" "}
          <span className="text-ink">Run depreciation</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Run depreciation</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="fiscal-period" className="mb-1 block text-xs font-medium text-ink-muted">
            Fiscal period
          </label>
          <select
            id="fiscal-period"
            value={fiscalPeriodId}
            onChange={(event) => setFiscalPeriodId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="">Select period</option>
            {(fiscalPeriods.data?.items ?? []).map((period) => (
              <option key={period.id} value={period.id}>
                {period.name} ({period.start_date} – {period.end_date})
              </option>
            ))}
          </select>
        </div>
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
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || runDepreciation.isPending || awaitingJob}
        className="mt-6 btn-ink"
      >
        {awaitingJob ? "Processing large run…" : runDepreciation.isPending ? "Running…" : "Run depreciation"}
      </button>
    </div>
  );
}
