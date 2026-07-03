/**
 * The line editor for a draft vendor bill (module-specific composite, STRUCTURE §4). Unlike
 * journal lines, a bill line is single-sided (net_amount on one expense/AP-side account) plus
 * an optional tax code the service uses to compute tax_amount — no debit/credit split, no
 * balance check here (the bill's gross total is derived server-side).
 */

import type { TaxCode, VendorBillLineCreate } from "@/modules/finance/types";
import type { Account } from "@/modules/finance/types";

export interface BillLinesEditorProps {
  lines: VendorBillLineCreate[];
  accounts: Account[];
  taxCodes: TaxCode[];
  onChange: (lines: VendorBillLineCreate[]) => void;
}

function emptyLine(): VendorBillLineCreate {
  return { account_id: "", net_amount: "" };
}

export function BillLinesEditor({ lines, accounts, taxCodes, onChange }: BillLinesEditorProps) {
  const updateLine = (index: number, patch: Partial<VendorBillLineCreate>) => {
    onChange(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  };
  const removeLine = (index: number) => {
    onChange(lines.filter((_, i) => i !== index));
  };
  const total = lines.reduce((sum, line) => sum + (Number(line.net_amount) || 0), 0);

  return (
    <div>
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.02em] text-ink-muted">
            <th className="py-2 pr-2">Account</th>
            <th className="py-2 pr-2">Description</th>
            <th className="py-2 pr-2">Tax code</th>
            <th className="w-32 py-2 pr-2 text-right">Net amount</th>
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
                  value={line.tax_code_id ?? ""}
                  onChange={(event) =>
                    updateLine(index, { tax_code_id: event.target.value || null })
                  }
                  className="w-full rounded-control border border-line bg-surface px-2 py-1 text-sm"
                >
                  <option value="">None</option>
                  {taxCodes.map((tax) => (
                    <option key={tax.id} value={tax.id}>
                      {tax.code} ({tax.rate_percent}%)
                    </option>
                  ))}
                </select>
              </td>
              <td className="py-1.5 pr-2">
                <input
                  type="number"
                  step="0.01"
                  value={line.net_amount}
                  onChange={(event) => updateLine(index, { net_amount: event.target.value })}
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
      <div className="mt-3 text-right text-sm tabular-nums text-ink-muted">
        Net total {total.toFixed(2)} (tax computed on post)
      </div>
    </div>
  );
}
