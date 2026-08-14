/**
 * Import a bank statement CSV (STRUCTURE §4). The backend endpoint takes the whole CSV as a
 * `csv_text` JSON string field, not multipart — this reads the chosen file as text and sends
 * it that way. Small files (<= sync cap) return the finished statement directly (201); larger
 * ones return a job to poll (202, PERFORMANCE §3) — this page handles both response shapes.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { pollJob } from "@/lib/jobs";
import { useBankAccountOptions, useImportBankStatement } from "@/modules/finance/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function BankStatementImportPage() {
  const navigate = useNavigate();
  const bankAccounts = useBankAccountOptions();
  const importStatement = useImportBankStatement();

  const [bankAccountId, setBankAccountId] = useState("");
  const [statementDate, setStatementDate] = useState(today());
  const [openingBalance, setOpeningBalance] = useState("");
  const [closingBalance, setClosingBalance] = useState("");
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [awaitingJob, setAwaitingJob] = useState(false);

  const canSubmit = Boolean(bankAccountId && openingBalance && closingBalance && file);

  const submit = async () => {
    if (!file) return;
    setError(null);
    try {
      const csvText = await file.text();
      const result = await importStatement.mutateAsync({
        bank_account_id: bankAccountId,
        statement_date: statementDate,
        opening_balance: openingBalance,
        closing_balance: closingBalance,
        currency_code: currencyCode,
        csv_text: csvText,
        source_filename: file.name,
      });

      if ("job_id" in result) {
        setAwaitingJob(true);
        const job = await pollJob<{ statement_id: string; line_count: number }>(result.job_id);
        setAwaitingJob(false);
        if (job.status === "FAILED") {
          setError(job.error ?? "Import failed.");
          return;
        }
        const statementId = job.result?.statement_id;
        if (statementId) {
          void navigate({ to: "/finance/bank-statements/$statementId", params: { statementId } });
        }
        return;
      }

      void navigate({ to: "/finance/bank-statements/$statementId", params: { statementId: result.id } });
    } catch (caught) {
      setAwaitingJob(false);
      setError(caught instanceof ApiError ? caught.message : "Unable to import the statement.");
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/bank-statements">Bank Statements</Link> /{" "}
          <span className="text-ink">Import bank statement</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Import bank statement</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="bank-account" className="mb-1 block text-xs font-medium text-ink-muted">
            Bank account
          </label>
          <select
            id="bank-account"
            value={bankAccountId}
            onChange={(event) => setBankAccountId(event.target.value)}
            className={CONTROL}
          >
            <option value="">Select account</option>
            {(bankAccounts.data ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} — {account.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="statement-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Statement date
          </label>
          <input
            id="statement-date"
            type="date"
            value={statementDate}
            onChange={(event) => setStatementDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="opening-balance" className="mb-1 block text-xs font-medium text-ink-muted">
            Opening balance
          </label>
          <input
            id="opening-balance"
            type="number"
            step="0.01"
            value={openingBalance}
            onChange={(event) => setOpeningBalance(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="closing-balance" className="mb-1 block text-xs font-medium text-ink-muted">
            Closing balance
          </label>
          <input
            id="closing-balance"
            type="number"
            step="0.01"
            value={closingBalance}
            onChange={(event) => setClosingBalance(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="currency" className="mb-1 block text-xs font-medium text-ink-muted">
            Currency
          </label>
          <input
            id="currency"
            type="text"
            value={currencyCode}
            onChange={(event) => setCurrencyCode(event.target.value.toUpperCase())}
            maxLength={3}
            className={CONTROL}
          />
        </div>
        <div className="col-span-2">
          <label htmlFor="csv-file" className="mb-1 block text-xs font-medium text-ink-muted">
            CSV file
          </label>
          <input
            id="csv-file"
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className={CONTROL}
          />
          <p className="mt-1 text-xs text-ink-muted">
            Header row: value_date,amount,description,counterparty_ref. Amount is signed — positive
            for money in, negative for money out.
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || importStatement.isPending || awaitingJob}
        className="mt-6 btn-ink"
      >
        {awaitingJob ? "Processing large file…" : importStatement.isPending ? "Importing…" : "Import"}
      </button>
    </div>
  );
}
