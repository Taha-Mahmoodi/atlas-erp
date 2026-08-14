/**
 * Create a draft customer invoice (STRUCTURE §4) — the AR mirror of VendorBillFormPage.
 * No edit path — invoices are create-then-post only (no PATCH endpoint).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { useAccountOptions, useCreateCustomerInvoice, useTaxCodes } from "@/modules/finance/hooks";
import { InvoiceLinesEditor } from "@/modules/finance/components/InvoiceLinesEditor";
import type { CustomerInvoiceLineCreate } from "@/modules/finance/types";
import { useCustomerOptions } from "@/modules/sales/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function CustomerInvoiceFormPage() {
  const navigate = useNavigate();
  const customers = useCustomerOptions();
  const accounts = useAccountOptions();
  const taxCodes = useTaxCodes();
  const createInvoice = useCreateCustomerInvoice();

  const [partnerId, setPartnerId] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(today());
  const [dueDate, setDueDate] = useState(today());
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [arAccountId, setArAccountId] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState<CustomerInvoiceLineCreate[]>([{ account_id: "", net_amount: "" }]);
  const [error, setError] = useState<string | null>(null);

  const validLines = lines.filter((line) => line.account_id && (Number(line.net_amount) || 0) > 0);
  const canSubmit = Boolean(partnerId && arAccountId && validLines.length > 0);

  const submit = async () => {
    setError(null);
    try {
      const customer = customers.data?.items.find((c) => c.id === partnerId);
      const invoice = await createInvoice.mutateAsync({
        partner_id: partnerId,
        partner_name: customer?.name ?? "",
        invoice_date: invoiceDate,
        due_date: dueDate,
        currency_code: currencyCode,
        ar_account_id: arAccountId,
        external_ref: externalRef || null,
        description: description || null,
        lines: validLines,
      });
      void navigate({ to: "/finance/customer-invoices/$invoiceId", params: { invoiceId: invoice.id } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the invoice.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance/customer-invoices">Customer Invoices</Link> /{" "}
          <span className="text-ink">New customer invoice</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">New customer invoice</h1>
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
            onChange={(event) => setPartnerId(event.target.value)}
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
          <label htmlFor="ar-account" className="mb-1 block text-xs font-medium text-ink-muted">
            AR account
          </label>
          <select
            id="ar-account"
            value={arAccountId}
            onChange={(event) => setArAccountId(event.target.value)}
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
          <label htmlFor="external-ref" className="mb-1 block text-xs font-medium text-ink-muted">
            Your reference
          </label>
          <input
            id="external-ref"
            type="text"
            value={externalRef}
            onChange={(event) => setExternalRef(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="invoice-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Invoice date
          </label>
          <input
            id="invoice-date"
            type="date"
            value={invoiceDate}
            onChange={(event) => setInvoiceDate(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div>
          <label htmlFor="due-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Due date
          </label>
          <input
            id="due-date"
            type="date"
            value={dueDate}
            onChange={(event) => setDueDate(event.target.value)}
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
        <div className="col-span-3">
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
        <InvoiceLinesEditor
          lines={lines}
          accounts={accounts.data?.items ?? []}
          taxCodes={taxCodes.data?.items ?? []}
          onChange={setLines}
        />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createInvoice.isPending}
        className="mt-6 btn-ink"
      >
        {createInvoice.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
