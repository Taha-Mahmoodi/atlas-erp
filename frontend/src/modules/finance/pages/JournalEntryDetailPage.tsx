/**
 * Journal entry detail (STRUCTURE §4): header, lines, and the Post / Reverse actions gated
 * by both the entry's status and the caller's permissions. Read-only lines resolve
 * account_id -> code/name via `useAccountLookup` (an unfiltered list — a posted line may
 * reference a non-postable or since-deactivated account).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useAccountLookup,
  useJournalEntry,
  usePostJournalEntry,
  useReverseJournalEntry,
} from "@/modules/finance/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function JournalEntryDetailPage() {
  const { entryId } = useParams({ strict: false });
  const navigate = useNavigate();
  const me = useMe();
  const entry = useJournalEntry(entryId);
  const accounts = useAccountLookup();
  const postEntry = usePostJournalEntry(entryId ?? "");
  const reverseEntry = useReverseJournalEntry(entryId ?? "");

  const [reversing, setReversing] = useState(false);
  const [reversalDate, setReversalDate] = useState(today());
  const [reversalDescription, setReversalDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  // TanStack Router reuses this component instance across navigations within the same
  // `/finance/journal-entries/$entryId` route (e.g. reversing an entry navigates here with a
  // new id) — reset the local UI state whenever the id changes so a leftover open reversal
  // panel / stale error from the PREVIOUS entry doesn't bleed into the new one.
  useEffect(() => {
    setReversing(false);
    setReversalDate(today());
    setReversalDescription("");
    setError(null);
  }, [entryId]);

  if (entry.isPending || !entry.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = entry.data;
  const permissions = me.data?.permissions ?? [];
  const accountLabel = (accountId: string) => {
    const account = accounts.data?.items.find((a) => a.id === accountId);
    return account ? `${account.code} — ${account.name}` : accountId;
  };

  const post = async () => {
    setError(null);
    try {
      await postEntry.mutateAsync();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to post the entry.");
    }
  };

  const reverse = async () => {
    setError(null);
    try {
      const reversal = await reverseEntry.mutateAsync({
        reversal_date: reversalDate,
        description: reversalDescription || null,
      });
      void navigate({ to: "/finance/journal-entries/$entryId", params: { entryId: reversal.id } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to reverse the entry.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{data.entry_number ?? "Draft entry"}</h1>
        <div className="flex gap-2">
          {data.status === "DRAFT" && permissions.includes("finance.journal.post") && (
            <button
              type="button"
              onClick={() => void post()}
              disabled={postEntry.isPending}
              className="btn-ink"
            >
              {postEntry.isPending ? "Posting…" : "Post entry"}
            </button>
          )}
          {data.status === "POSTED" &&
            permissions.includes("finance.journal.reverse") &&
            !data.reversed_by_entry_id && (
              <button
                type="button"
                onClick={() => setReversing((prev) => !prev)}
                className="btn-chip"
              >
                Reverse
              </button>
            )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      {reversing && (
        <div className="mt-4 rounded-card border border-line bg-panel p-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="reversal-date" className="mb-1 block text-xs font-medium text-ink-muted">
                Reversal date
              </label>
              <input
                id="reversal-date"
                type="date"
                value={reversalDate}
                onChange={(event) => setReversalDate(event.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm"
              />
            </div>
            <div>
              <label htmlFor="reversal-description" className="mb-1 block text-xs font-medium text-ink-muted">
                Description
              </label>
              <input
                id="reversal-description"
                type="text"
                value={reversalDescription}
                onChange={(event) => setReversalDescription(event.target.value)}
                className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm"
              />
            </div>
          </div>
          <button
            type="button"
            onClick={() => void reverse()}
            disabled={reverseEntry.isPending}
            className="mt-3 rounded-control bg-danger px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {reverseEntry.isPending ? "Reversing…" : "Confirm reversal"}
          </button>
        </div>
      )}

      <dl className="mt-6 grid grid-cols-3 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Posting date</dt>
          <dd className="text-ink">{formatDate(data.posting_date)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Status</dt>
          <dd className="text-ink">{data.status}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Type</dt>
          <dd className="text-ink">{data.document_type}</dd>
        </div>
        <div className="col-span-3">
          <dt className="text-xs text-ink-muted">Description</dt>
          <dd className="text-ink">{data.description ?? "—"}</dd>
        </div>
        {data.reverses_entry_id && (
          <div>
            <dt className="text-xs text-ink-muted">Reverses</dt>
            <dd>
              <Link
                to="/finance/journal-entries/$entryId"
                params={{ entryId: data.reverses_entry_id }}
                className="text-primary hover:underline"
              >
                View original
              </Link>
            </dd>
          </div>
        )}
        {data.reversed_by_entry_id && (
          <div>
            <dt className="text-xs text-ink-muted">Reversed by</dt>
            <dd>
              <Link
                to="/finance/journal-entries/$entryId"
                params={{ entryId: data.reversed_by_entry_id }}
                className="text-primary hover:underline"
              >
                View reversal
              </Link>
            </dd>
          </div>
        )}
      </dl>

      <table className="mt-6 w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2 text-right">Debit</th>
            <th className="py-2 pr-2 text-right">Credit</th>
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line) => (
            <tr key={line.id} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2 text-ink">{accountLabel(line.account_id)}</td>
              <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                {Number(line.transaction_debit_amount) > 0
                  ? formatMoney(line.transaction_debit_amount, line.currency_code)
                  : "—"}
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                {Number(line.transaction_credit_amount) > 0
                  ? formatMoney(line.transaction_credit_amount, line.currency_code)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
