/**
 * Renders a list of `StatementGroup`s (account-group headers + line rows + subtotal) shared by
 * the P&L and balance sheet pages (STRUCTURE §4) — pure presentation over an identical response
 * shape, unlike BillLinesEditor/InvoiceLinesEditor which stay separate because AP and AR are
 * different domain aggregates. There's no domain distinction here to preserve.
 */

import { formatMoney } from "@/lib/format";
import type { StatementGroup } from "@/modules/finance/types";

export interface StatementGroupTableProps {
  groups: StatementGroup[];
  total: string;
  totalLabel: string;
  currencyCode: string;
}

export function StatementGroupTable({ groups, total, totalLabel, currencyCode }: StatementGroupTableProps) {
  if (groups.length === 0) {
    return (
      <table className="w-full border-collapse text-[13px]">
        <tbody>
          <tr>
            <td className="py-4 text-sm text-ink-muted">No activity.</td>
          </tr>
        </tbody>
      </table>
    );
  }

  return (
    <table className="w-full border-collapse text-[13px]">
      {groups.map((group) => (
        <tbody key={group.group_code}>
          <tr>
            <td colSpan={2} className="px-3 pt-3 pb-1 mono-caps text-ink-muted">
              {group.group_name}
            </td>
          </tr>
          {group.lines.map((line) => (
            <tr key={line.account_id} className="border-b border-line last:border-b-0">
              <td className="py-1 pl-3 pr-2 text-ink">
                {line.account_code} — {line.account_name}
              </td>
              <td className="py-1 pr-3 text-right tabular-nums text-ink">
                {formatMoney(line.amount, currencyCode)}
              </td>
            </tr>
          ))}
          <tr className="border-b border-line">
            <td className="py-1 pl-3 pr-2 text-right text-xs font-medium text-ink-muted">Subtotal</td>
            <td className="py-1 pr-3 text-right tabular-nums text-xs font-medium text-ink-muted">
              {formatMoney(group.subtotal, currencyCode)}
            </td>
          </tr>
        </tbody>
      ))}
      <tbody>
        <tr>
          <td className="px-3 pt-3 text-right font-semibold text-ink">{totalLabel}</td>
          <td className="pr-3 pt-3 text-right tabular-nums font-semibold text-ink">
            {formatMoney(total, currencyCode)}
          </td>
        </tr>
      </tbody>
    </table>
  );
}
