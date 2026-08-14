/**
 * Create + post a customer receipt (STRUCTURE §4) — the AR mirror of VendorPaymentFormPage.
 * The receipt amount is DERIVED from the sum of entered allocations so the backend's
 * amount==Σallocations invariant (#73) can't be violated from this form. No detail route: the
 * backend exposes no GET /customer-receipts/{id} — success shows an inline confirmation.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useAccountOptions, useCreateCustomerReceipt, useOpenCustomerInvoices } from "@/modules/finance/hooks";
import type { CustomerReceiptDetail } from "@/modules/finance/types";
import { useCustomerOptions } from "@/modules/sales/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CustomerReceiptFormPage() {
  const customers = useCustomerOptions();
  const accounts = useAccountOptions();
  const createReceipt = useCreateCustomerReceipt();

  const [partnerId, setPartnerId] = useState("");
  const [bankAccountId, setBankAccountId] = useState("");
  const [receiptDate, setReceiptDate] = useState(today());
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [description, setDescription] = useState("");
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<CustomerReceiptDetail | null>(null);
  // A receipt invalidates the customer's open-invoices query, and a fully-paid invoice then
  // drops out of that list — the success panel resolves invoice numbers from a snapshot taken
  // AT SUBMIT TIME, not from the (by-then-refetched) live query (mirrors the AP payment fix).
  const [invoiceNumbers, setInvoiceNumbers] = useState<Record<string, string>>({});

  const openInvoices = useOpenCustomerInvoices(partnerId || undefined);

  const activeAllocations = Object.entries(allocations).filter(([, amount]) => Number(amount) > 0);
  const total = activeAllocations.reduce((sum, [, amount]) => sum + Number(amount), 0);
  const canSubmit = Boolean(partnerId && bankAccountId && activeAllocations.length > 0);

  const submit = async () => {
    setError(null);
    try {
      const customer = customers.data?.items.find((c) => c.id === partnerId);
      setInvoiceNumbers(
        Object.fromEntries(
          (openInvoices.data ?? []).map((invoice) => [invoice.id, invoice.invoice_number ?? invoice.id]),
        ),
      );
      const receipt = await createReceipt.mutateAsync({
        partner_id: partnerId,
        partner_name: customer?.name ?? "",
        receipt_date: receiptDate,
        currency_code: currencyCode,
        bank_account_id: bankAccountId,
        amount: total.toFixed(2),
        description: description || null,
        allocations: activeAllocations.map(([invoiceId, amount]) => ({ invoice_id: invoiceId, amount })),
      });
      setPosted(receipt);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the receipt.");
    }
  };

  if (posted) {
    return (
      <div className="mx-auto max-w-2xl">
        <header className="mb-6">
          <p className="text-[12px] text-ink-muted">
            <Link to="/finance/customer-receipts">Customer Receipts</Link> /{" "}
            <span className="text-ink">Receipt posted</span>
          </p>
          <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">Receipt posted</h1>
        </header>
        <div className="rounded-card border border-line bg-surface px-[18px] py-4 shadow-card">
          <p className="text-sm text-ink">
            <span className="font-medium">{posted.receipt_number}</span> for{" "}
            {formatMoney(posted.amount, posted.currency_code)} from {posted.partner_name}
          </p>
          <table className="mt-3 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left mono-caps text-ink-muted">
                <th className="py-1.5 pr-2">Invoice</th>
                <th className="py-1.5 pr-2 text-right">Allocated</th>
              </tr>
            </thead>
            <tbody>
              {posted.allocations.map((allocation) => (
                <tr key={allocation.id} className="border-b border-line last:border-b-0">
                  <td className="py-1.5 pr-2 text-ink-muted">
                    {invoiceNumbers[allocation.customer_invoice_id] ?? allocation.customer_invoice_id}
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                    {formatMoney(allocation.allocated_amount, posted.currency_code)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex gap-4 text-sm">
          <Link to="/finance/customer-invoices" className="text-primary hover:underline">
            View customer invoices
          </Link>
          <Link to="/finance/customer-receipts" className="text-primary hover:underline">
            View receipts
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/customer-receipts">Customer Receipts</Link> /{" "}
          <span className="text-ink">New customer receipt</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New customer receipt</h1>
      </header>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="customer" className="mb-1 block text-xs font-medium text-ink-muted">
            Customer
          </label>
          <select
            id="customer"
            value={partnerId}
            onChange={(event) => {
              setPartnerId(event.target.value);
              setAllocations({});
            }}
            className={CONTROL}
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
            {(accounts.data?.items ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {account.code} — {account.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="receipt-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Receipt date
          </label>
          <input
            id="receipt-date"
            type="date"
            value={receiptDate}
            onChange={(event) => setReceiptDate(event.target.value)}
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

      {partnerId && (
        <div className="mt-6">
          <h2 className="mono-caps text-ink-muted">
            Open invoices
          </h2>
          {openInvoices.isPending ? (
            <p className="mt-2 text-[13px] text-ink-muted">Loading…</p>
          ) : (openInvoices.data ?? []).length === 0 ? (
            <p className="mt-2 text-[13px] text-ink-muted">This customer has no open invoices.</p>
          ) : (
            <table className="mt-2 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left mono-caps text-ink-muted">
                  <th className="py-2 pr-2">Invoice #</th>
                  <th className="py-2 pr-2">Due date</th>
                  <th className="py-2 pr-2 text-right">Open amount</th>
                  <th className="w-32 py-2 pr-2 text-right">Receive</th>
                </tr>
              </thead>
              <tbody>
                {(openInvoices.data ?? []).map((invoice) => (
                  <tr key={invoice.id} className="border-b border-line last:border-b-0">
                    <td className="py-1.5 pr-2 text-ink">{invoice.invoice_number}</td>
                    <td className="py-1.5 pr-2 text-ink-muted">{formatDate(invoice.due_date)}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                      {formatMoney(invoice.open_amount, invoice.currency_code)}
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="number"
                        step="0.01"
                        value={allocations[invoice.id] ?? ""}
                        onChange={(event) =>
                          setAllocations((prev) => ({ ...prev, [invoice.id]: event.target.value }))
                        }
                        className="w-full rounded-control border border-line bg-surface px-2 py-1 text-right text-sm tabular-nums"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="mt-3 text-right text-sm font-medium tabular-nums text-ink">
            Total receipt: {total.toFixed(2)} {currencyCode}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createReceipt.isPending}
        className="mt-6 btn-ink"
      >
        {createReceipt.isPending ? "Receiving…" : "Create receipt"}
      </button>
    </div>
  );
}
