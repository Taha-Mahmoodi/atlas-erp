/**
 * Price quote lookup (STRUCTURE §4): a read-only simulation over `GET /sales/price-quote` — no
 * document is created here. Answers "what would this customer actually pay for this item at
 * this quantity/date", resolving against whichever ACTIVE price list wins (highest priority,
 * then group-targeted over general, then latest valid_from). Later slices call this same
 * resolution internally when pricing a quote/order line; this page exposes it standalone.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney, formatQuantity } from "@/lib/format";
import { useItemOptions } from "@/modules/inventory/hooks";
import { useCustomerOptions, usePriceQuote } from "@/modules/sales/hooks";
import type { PriceQuoteParams } from "@/modules/sales/api";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function PriceQuoteLookupPage() {
  const customers = useCustomerOptions();
  const items = useItemOptions();

  const [customerId, setCustomerId] = useState("");
  const [itemId, setItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [date, setDate] = useState(today());

  const params: PriceQuoteParams | undefined =
    customerId && itemId && Number(quantity) > 0
      ? { customer_id: customerId, item_id: itemId, quantity, date }
      : undefined;
  const quote = usePriceQuote(params);

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales">Sales</Link> / <span className="text-ink">Price Quote</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Price Quote</h1>
        </div>
        <p className="mt-1 text-[13px] text-ink-muted">
          Look up what a customer would actually pay for an item — resolves against price lists
          without creating any document.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="quote-customer" className="mb-1 block text-xs font-medium text-ink-muted">
            Customer
          </label>
          <select
            id="quote-customer"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="">Select customer</option>
            {(customers.data?.items ?? []).map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.customer_code} — {customer.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="quote-item" className="mb-1 block text-xs font-medium text-ink-muted">
            Item
          </label>
          <select
            id="quote-item"
            value={itemId}
            onChange={(event) => setItemId(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          >
            <option value="">Select item</option>
            {(items.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.item_code} — {item.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="quote-quantity" className="mb-1 block text-xs font-medium text-ink-muted">
            Quantity
          </label>
          <input
            id="quote-quantity"
            type="number"
            step="0.000001"
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label htmlFor="quote-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Date
          </label>
          <input
            id="quote-date"
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            className="w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
          />
        </div>
      </div>

      {params && (
        <div className="mt-6 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
          {quote.isPending ? (
            <p className="text-[13px] text-ink-muted">Resolving…</p>
          ) : quote.data?.matched ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
              <div>
                <dt className="mono-caps text-ink-muted">Unit price</dt>
                <dd className="mt-1.5 text-[13px] text-ink tabular-nums">
                  {formatMoney(quote.data.unit_price ?? "0", quote.data.currency_code ?? "—")}
                </dd>
              </div>
              <div>
                <dt className="mono-caps text-ink-muted">Quantity</dt>
                <dd className="mt-1.5 text-[13px] text-ink tabular-nums">{formatQuantity(quote.data.quantity)}</dd>
              </div>
              <div>
                <dt className="mono-caps text-ink-muted">Price list</dt>
                <dd className="mt-1.5 text-[13px] text-ink">{quote.data.price_list_code}</dd>
              </div>
            </dl>
          ) : (
            <p className="text-[13px] text-ink-muted">
              No price list matches this customer, item, quantity, and date.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
