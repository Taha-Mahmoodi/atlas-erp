/**
 * Create + post a vendor payment (STRUCTURE §4). Selecting a vendor loads its open bills;
 * the payment amount is DERIVED from the sum of entered allocations (not a separately typed
 * field) so the amount == Σallocations invariant the backend enforces (#73) can never be
 * violated from this form. The backend has no GET /vendor-payments/{id} — a payment posts in
 * one step and its allocations are only ever returned by the create call itself — so success
 * shows an inline confirmation here rather than navigating to a detail route that couldn't
 * re-fetch anything.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { formatDate, formatMoney } from "@/lib/format";
import { useAccountOptions, useCreateVendorPayment, useOpenVendorBills } from "@/modules/finance/hooks";
import type { VendorPaymentDetail } from "@/modules/finance/types";
import { useVendorOptions } from "@/modules/procurement/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function VendorPaymentFormPage() {
  const vendors = useVendorOptions();
  const accounts = useAccountOptions();
  const createPayment = useCreateVendorPayment();

  const [partnerId, setPartnerId] = useState("");
  const [bankAccountId, setBankAccountId] = useState("");
  const [paymentDate, setPaymentDate] = useState(today());
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [description, setDescription] = useState("");
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [posted, setPosted] = useState<VendorPaymentDetail | null>(null);
  // A payment invalidates the vendor's open-bills query, and a fully-paid bill then drops out
  // of that list — so the success panel resolves bill numbers from a snapshot taken AT SUBMIT
  // TIME, not from the (by-then-refetched) live query.
  const [billNumbers, setBillNumbers] = useState<Record<string, string>>({});

  const openBills = useOpenVendorBills(partnerId || undefined);

  const activeAllocations = Object.entries(allocations).filter(([, amount]) => Number(amount) > 0);
  const total = activeAllocations.reduce((sum, [, amount]) => sum + Number(amount), 0);
  const canSubmit = Boolean(partnerId && bankAccountId && activeAllocations.length > 0);

  const submit = async () => {
    setError(null);
    try {
      const vendor = vendors.data?.items.find((v) => v.id === partnerId);
      setBillNumbers(
        Object.fromEntries((openBills.data ?? []).map((bill) => [bill.id, bill.bill_number ?? bill.id])),
      );
      const payment = await createPayment.mutateAsync({
        partner_id: partnerId,
        partner_name: vendor?.name ?? "",
        payment_date: paymentDate,
        currency_code: currencyCode,
        bank_account_id: bankAccountId,
        amount: total.toFixed(2),
        description: description || null,
        allocations: activeAllocations.map(([billId, amount]) => ({ bill_id: billId, amount })),
      });
      setPosted(payment);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the payment.");
    }
  };

  if (posted) {
    return (
      <div className="mx-auto max-w-2xl">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Payment posted</h1>
        <div className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card">
          <p className="text-sm text-ink">
            <span className="font-medium">{posted.payment_number}</span> for{" "}
            {formatMoney(posted.amount, posted.currency_code)} to {posted.partner_name}
          </p>
          <table className="mt-3 w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-line text-left mono-caps text-ink-muted">
                <th className="py-1.5 pr-2">Bill</th>
                <th className="py-1.5 pr-2 text-right">Allocated</th>
              </tr>
            </thead>
            <tbody>
              {posted.allocations.map((allocation) => (
                <tr key={allocation.id} className="border-b border-line last:border-b-0">
                  <td className="py-1.5 pr-2 text-ink-muted">
                    {billNumbers[allocation.vendor_bill_id] ?? allocation.vendor_bill_id}
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
          <Link to="/finance/vendor-bills" className="text-primary hover:underline">
            View vendor bills
          </Link>
          <Link to="/finance/vendor-payments" className="text-primary hover:underline">
            View payments
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New vendor payment</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="vendor" className="mb-1 block text-xs font-medium text-ink-muted">
            Vendor
          </label>
          <select
            id="vendor"
            value={partnerId}
            onChange={(event) => {
              setPartnerId(event.target.value);
              setAllocations({});
            }}
            className={CONTROL}
          >
            <option value="">Select vendor</option>
            {(vendors.data?.items ?? []).map((vendor) => (
              <option key={vendor.id} value={vendor.id}>
                {vendor.vendor_code} — {vendor.name}
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
          <label htmlFor="payment-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Payment date
          </label>
          <input
            id="payment-date"
            type="date"
            value={paymentDate}
            onChange={(event) => setPaymentDate(event.target.value)}
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
            Open bills
          </h2>
          {openBills.isPending ? (
            <p className="mt-2 text-sm text-ink-muted">Loading…</p>
          ) : (openBills.data ?? []).length === 0 ? (
            <p className="mt-2 text-sm text-ink-muted">This vendor has no open bills.</p>
          ) : (
            <table className="mt-2 w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b border-line text-left mono-caps text-ink-muted">
                  <th className="py-2 pr-2">Bill #</th>
                  <th className="py-2 pr-2">Due date</th>
                  <th className="py-2 pr-2 text-right">Open amount</th>
                  <th className="w-32 py-2 pr-2 text-right">Pay</th>
                </tr>
              </thead>
              <tbody>
                {(openBills.data ?? []).map((bill) => (
                  <tr key={bill.id} className="border-b border-line last:border-b-0">
                    <td className="py-1.5 pr-2 text-ink">{bill.bill_number}</td>
                    <td className="py-1.5 pr-2 text-ink-muted">{formatDate(bill.due_date)}</td>
                    <td className="py-1.5 pr-2 text-right tabular-nums text-ink">
                      {formatMoney(bill.open_amount, bill.currency_code)}
                    </td>
                    <td className="py-1.5 pr-2">
                      <input
                        type="number"
                        step="0.01"
                        value={allocations[bill.id] ?? ""}
                        onChange={(event) =>
                          setAllocations((prev) => ({ ...prev, [bill.id]: event.target.value }))
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
            Total payment: {total.toFixed(2)} {currencyCode}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createPayment.isPending}
        className="mt-6 btn-ink"
      >
        {createPayment.isPending ? "Paying…" : "Create payment"}
      </button>
    </div>
  );
}
