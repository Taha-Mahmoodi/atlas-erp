/**
 * The balanced-lines editor for a draft journal entry (module-specific composite, STRUCTURE
 * §4 — not design-system material, it knows about accounts/debits/credits). A live
 * debit-vs-credit indicator is advisory only (plain JS number arithmetic on user-typed
 * strings, D-015 doesn't apply to display hints); the raw strings the user typed are what
 * actually get posted to the API, untouched.
 */

import type { Account, JournalLineCreate } from "@/modules/finance/types";
import type { WbsElement } from "@/modules/projects/types";

export interface JournalLinesEditorProps {
  lines: JournalLineCreate[];
  accounts: Account[];
  /** WBS-element options for the per-line project dimension (of the page's selected project). */
  wbsElements: WbsElement[];
  onChange: (lines: JournalLineCreate[]) => void;
}

function emptyLine(): JournalLineCreate {
  return { account_id: "", transaction_debit_amount: "", transaction_credit_amount: "" };
}

function sum(lines: JournalLineCreate[], field: "transaction_debit_amount" | "transaction_credit_amount") {
  return lines.reduce((total, line) => total + (Number(line[field]) || 0), 0);
}

export function JournalLinesEditor({ lines, accounts, wbsElements, onChange }: JournalLinesEditorProps) {
  const updateLine = (index: number, patch: Partial<JournalLineCreate>) => {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  };
  const removeLine = (index: number) => {
    onChange(lines.filter((_, i) => i !== index));
  };

  const totalDebit = sum(lines, "transaction_debit_amount");
  const totalCredit = sum(lines, "transaction_credit_amount");
  const balanced = lines.length >= 2 && totalDebit === totalCredit && totalDebit > 0;

  return (
    <div>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left mono-caps text-ink-muted">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2">WBS element</th>
            <th className="w-32 py-2 pr-2 text-right">Debit</th>
            <th className="w-32 py-2 pr-2 text-right">Credit</th>
            <th className="w-10 py-2" />
          </tr>
        </thead>
        <tbody>
          {lines.map((line, index) => (
            // eslint-disable-next-line react/no-array-index-key -- lines have no stable id pre-save
            <tr key={index} className="border-b border-line last:border-b-0">
              <td className="py-1.5 pr-2">
                <select
                  value={line.account_id}
                  onChange={(event) => updateLine(index, { account_id: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                >
                  <option value="">Select account</option>
                  {accounts.map((account) => (
                    <option key={account.id} value={account.id}>
                      {account.code} — {account.name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="text"
                  value={line.description ?? ""}
                  onChange={(event) => updateLine(index, { description: event.target.value })}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                />
              </td>
              <td className="py-1.5 pr-2">
                <select
                  aria-label="WBS element"
                  value={line.project_id ?? ""}
                  onChange={(event) => updateLine(index, { project_id: event.target.value || null })}
                  disabled={wbsElements.length === 0}
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm disabled:opacity-45"
                >
                  <option value="">None</option>
                  {wbsElements.map((wbs) => (
                    <option key={wbs.id} value={wbs.id}>
                      {wbs.code} — {wbs.name}
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="number"
                  step="0.01"
                  value={line.transaction_debit_amount}
                  onChange={(event) =>
                    updateLine(index, { transaction_debit_amount: event.target.value, transaction_credit_amount: "" })
                  }
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                />
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="number"
                  step="0.01"
                  value={line.transaction_credit_amount}
                  onChange={(event) =>
                    updateLine(index, { transaction_credit_amount: event.target.value, transaction_debit_amount: "" })
                  }
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                />
              </td>
              <td className="py-1.5 text-center">
                <button
                  type="button"
                  onClick={() => removeLine(index)}
                  aria-label="Remove line"
                  className="text-ink-faint transition-colors duration-150 hover:text-danger"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() => onChange([...lines, emptyLine()])}
        className="mt-2 rounded-control px-2 py-1 text-sm font-medium text-primary transition-colors duration-150 hover:bg-primary-tint"
      >
        + Add line
      </button>
      <div className="mt-3 flex items-center justify-end gap-4 text-sm tabular-nums">
        <span className="text-ink-muted">Debit {totalDebit.toFixed(2)}</span>
        <span className="text-ink-muted">Credit {totalCredit.toFixed(2)}</span>
        <span className={balanced ? "font-medium text-success" : "font-medium text-warn"}>
          {balanced ? "Balanced" : `Out of balance by ${Math.abs(totalDebit - totalCredit).toFixed(2)}`}
        </span>
      </div>
    </div>
  );
}
