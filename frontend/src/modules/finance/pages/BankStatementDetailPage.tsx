/**
 * The bank reconciliation workbench (STRUCTURE §4). Matching is exclusively automatic
 * (suggest-matches) followed by confirm/reject — there's no manual bank-line <-> journal-line
 * pairing action in v1, no un-matching a MATCHED line, and no reopening a CLEARED one, so the
 * per-line actions here are intentionally just Confirm / Reject / Clear. Clear posts a real
 * journal entry using the server's default contra account (bank_unmatched_clearing) — an
 * override picker is a documented "later", not something this workbench needs yet.
 */

import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import {
  useBankStatement,
  useBankStatementLines,
  useClearLine,
  useConfirmMatch,
  useRejectSuggestion,
  useSuggestMatches,
} from "@/modules/finance/hooks";
import { StatusPill } from "@/components/StatusPill";

export function BankStatementDetailPage() {
  const { statementId } = useParams({ strict: false });
  const me = useMe();
  const canReconcile = (me.data?.permissions ?? []).includes("finance.bank.reconcile");
  const statement = useBankStatement(statementId);
  const lines = useBankStatementLines(statementId);
  const suggestMatches = useSuggestMatches(statementId ?? "");
  const confirmMatch = useConfirmMatch(statementId ?? "");
  const rejectSuggestion = useRejectSuggestion(statementId ?? "");
  const clearLine = useClearLine(statementId ?? "");
  const [error, setError] = useState<string | null>(null);
  const [actingOnLineId, setActingOnLineId] = useState<string | null>(null);

  if (statement.isPending || !statement.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = statement.data;
  const currencyCode = data.currency_code;

  const withErrorHandling = async (lineId: string, action: () => Promise<unknown>) => {
    setError(null);
    setActingOnLineId(lineId);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to complete that action.");
    } finally {
      setActingOnLineId(null);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Statement — {formatDate(data.statement_date)}</h1>
        {canReconcile && (
          <button
            type="button"
            onClick={() => void suggestMatches.mutateAsync()}
            disabled={suggestMatches.isPending}
            className="btn-ink"
          >
            {suggestMatches.isPending ? "Matching…" : "Suggest matches"}
          </button>
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
          <dd className="text-ink">{data.status.replace("_", " ")}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Opening balance</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.opening_balance, currencyCode)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Closing balance</dt>
          <dd className="tabular-nums text-ink">{formatMoney(data.closing_balance, currencyCode)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Progress</dt>
          <dd className="text-ink">
            {data.progress.resolved} / {data.progress.total} resolved
            {data.progress.suggested > 0 ? ` (${data.progress.suggested} suggested)` : ""}
          </dd>
        </div>
      </dl>

      <div className="mt-6 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line text-left mono-caps text-ink-muted">
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Description</th>
              <th className="px-3 py-2">Counterparty</th>
              <th className="px-3 py-2 text-right">Amount</th>
              <th className="px-3 py-2">Status</th>
              {canReconcile && <th className="px-3 py-2">Action</th>}
            </tr>
          </thead>
          <tbody>
            {lines.isPending ? (
              <tr>
                <td colSpan={canReconcile ? 6 : 5} className="px-4 py-10 text-center text-sm text-ink-muted">
                  Loading…
                </td>
              </tr>
            ) : (
              (lines.data?.items ?? []).map((line) => {
                const acting = actingOnLineId === line.id;
                return (
                  <tr key={line.id} className="border-b border-line last:border-b-0">
                    <td className="px-3 py-1.5 text-ink-muted">{formatDate(line.value_date)}</td>
                    <td className="px-3 py-1.5 text-ink">{line.description}</td>
                    <td className="px-3 py-1.5 text-ink-muted">{line.counterparty_ref ?? "—"}</td>
                    <td className={`px-3 py-1.5 text-right tabular-nums ${Number(line.amount) < 0 ? "text-danger" : "text-ink"}`}>
                      {formatMoney(line.amount, currencyCode)}
                    </td>
                    <td className="px-3 py-1.5">
                      <StatusPill status={line.status} />
                    </td>
                    {canReconcile && (
                      <td className="px-3 py-1.5">
                        {line.status === "SUGGESTED" && (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={acting}
                              onClick={() => void withErrorHandling(line.id, () => confirmMatch.mutateAsync(line.id))}
                              className="text-xs font-medium text-primary hover:underline disabled:opacity-45"
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              disabled={acting}
                              onClick={() => void withErrorHandling(line.id, () => rejectSuggestion.mutateAsync(line.id))}
                              className="text-xs font-medium text-danger hover:underline disabled:opacity-45"
                            >
                              Reject
                            </button>
                          </div>
                        )}
                        {line.status === "UNMATCHED" && (
                          <button
                            type="button"
                            disabled={acting}
                            onClick={() => void withErrorHandling(line.id, () => clearLine.mutateAsync({ lineId: line.id }))}
                            className="text-xs font-medium text-primary hover:underline disabled:opacity-45"
                          >
                            Clear
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
