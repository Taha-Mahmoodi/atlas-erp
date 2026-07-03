/**
 * Create a draft journal entry (STRUCTURE §4). The header fields are plain controls (not
 * FormBuilder — the lines editor is a custom table FormBuilder has no field type for);
 * `JournalLinesEditor` owns the balanced-lines UX. Draft creation isn't idempotency-gated on
 * the backend (api.ts's createJournalEntry docstring), so no key is needed here.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { JournalLinesEditor } from "@/modules/finance/components/JournalLinesEditor";
import { useAccountOptions, useCreateJournalEntry } from "@/modules/finance/hooks";
import type { JournalLineCreate } from "@/modules/finance/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function JournalEntryFormPage() {
  const navigate = useNavigate();
  const accounts = useAccountOptions();
  const createEntry = useCreateJournalEntry();

  const [postingDate, setPostingDate] = useState(today());
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState<JournalLineCreate[]>([
    { account_id: "", transaction_debit_amount: "", transaction_credit_amount: "" },
    { account_id: "", transaction_debit_amount: "", transaction_credit_amount: "" },
  ]);
  const [error, setError] = useState<string | null>(null);

  // The editor leaves the not-in-use side as "" for a cleaner empty cell while typing; the
  // backend's Decimal field rejects an empty string outright ("Input should be a valid
  // decimal") rather than treating it as its 0 default, so normalize here at the API
  // boundary — every line the server sees has both sides as real decimal strings.
  const validLines = lines
    .filter(
      (line) =>
        line.account_id &&
        ((Number(line.transaction_debit_amount) || 0) > 0 || (Number(line.transaction_credit_amount) || 0) > 0),
    )
    .map((line) => ({
      ...line,
      transaction_debit_amount: line.transaction_debit_amount || "0",
      transaction_credit_amount: line.transaction_credit_amount || "0",
    }));
  const totalDebit = validLines.reduce((sum, l) => sum + (Number(l.transaction_debit_amount) || 0), 0);
  const totalCredit = validLines.reduce((sum, l) => sum + (Number(l.transaction_credit_amount) || 0), 0);
  const canSubmit = validLines.length >= 2 && totalDebit === totalCredit && totalDebit > 0;

  const submit = async () => {
    setError(null);
    try {
      const entry = await createEntry.mutateAsync({
        posting_date: postingDate,
        currency_code: currencyCode,
        description: description || null,
        lines: validLines,
      });
      void navigate({ to: "/finance/journal-entries/$entryId", params: { entryId: entry.id } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the entry.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-ink">New journal entry</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="posting-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Posting date
          </label>
          <input
            id="posting-date"
            type="date"
            value={postingDate}
            onChange={(event) => setPostingDate(event.target.value)}
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
        <div>
          <label htmlFor="description" className="mb-1 block text-xs font-medium text-ink-muted">
            Description
          </label>
          <input
            id="description"
            type="text"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className={CONTROL}
          />
        </div>
      </div>

      <div className="mt-6">
        <JournalLinesEditor lines={lines} accounts={accounts.data?.items ?? []} onChange={setLines} />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createEntry.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createEntry.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
