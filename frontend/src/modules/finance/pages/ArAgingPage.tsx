/**
 * AR aging report (STRUCTURE §4) — the AP mirror. Open-invoice buckets per customer as of a
 * date, plus the rolled-up totals row. A pure projection — no create/edit actions.
 */

import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useArAging } from "@/modules/finance/hooks";
import { useCustomerOptions } from "@/modules/sales/hooks";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ArAgingPage() {
  const [asOf, setAsOf] = useState(today());
  const [partnerId, setPartnerId] = useState("");
  const customers = useCustomerOptions();
  const aging = useArAging(asOf, partnerId || undefined);

  const currency = aging.data?.partners[0]?.currency_code ?? "USD";

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">AR Aging</h1>

      <div className="mt-4 flex items-center gap-4">
        <input
          type="date"
          value={asOf}
          onChange={(event) => setAsOf(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
        <select
          value={partnerId}
          onChange={(event) => setPartnerId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All customers</option>
          {(customers.data?.items ?? []).map((customer) => (
            <option key={customer.id} value={customer.id}>
              {customer.customer_code} — {customer.name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4 overflow-x-auto rounded-card border border-line bg-surface shadow-card">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line text-left mono-caps text-ink-muted">
              <th className="px-3 py-2">Customer</th>
              <th className="px-3 py-2 text-right">Current</th>
              <th className="px-3 py-2 text-right">1-30</th>
              <th className="px-3 py-2 text-right">31-60</th>
              <th className="px-3 py-2 text-right">61-90</th>
              <th className="px-3 py-2 text-right">90+</th>
              <th className="px-3 py-2 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {aging.isPending ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-ink-muted">
                  Loading…
                </td>
              </tr>
            ) : (aging.data?.partners ?? []).length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-sm text-ink-muted">
                  No open invoices as of this date.
                </td>
              </tr>
            ) : (
              aging.data?.partners.map((bucket) => (
                <tr key={bucket.partner_id} className="border-b border-line last:border-b-0">
                  <td className="px-3 py-1.5 text-ink">{bucket.partner_name}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatMoney(bucket.current, bucket.currency_code)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatMoney(bucket.days_1_30, bucket.currency_code)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatMoney(bucket.days_31_60, bucket.currency_code)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatMoney(bucket.days_61_90, bucket.currency_code)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums">{formatMoney(bucket.days_over_90, bucket.currency_code)}</td>
                  <td className="px-3 py-1.5 text-right tabular-nums font-medium">{formatMoney(bucket.total, bucket.currency_code)}</td>
                </tr>
              ))
            )}
          </tbody>
          {aging.data && aging.data.partners.length > 0 && (
            <tfoot>
              <tr className="border-t border-line bg-panel font-medium">
                <td className="px-3 py-2 text-ink">Total</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.current, currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.days_1_30, currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.days_31_60, currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.days_61_90, currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.days_over_90, currency)}</td>
                <td className="px-3 py-2 text-right tabular-nums">{formatMoney(aging.data.total, currency)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}
