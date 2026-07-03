/**
 * Create a draft vendor bill (STRUCTURE §4). Plain header controls (mirrors
 * JournalEntryFormPage) + `BillLinesEditor` for the line items. No edit path — bills are
 * create-then-post only per the backend surface (no PATCH endpoint).
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { ApiError } from "@/lib/apiClient";
import { useAccountOptions, useCreateVendorBill, useTaxCodes } from "@/modules/finance/hooks";
import { BillLinesEditor } from "@/modules/finance/components/BillLinesEditor";
import type { VendorBillLineCreate } from "@/modules/finance/types";
import { useVendorOptions } from "@/modules/procurement/hooks";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function VendorBillFormPage() {
  const navigate = useNavigate();
  const vendors = useVendorOptions();
  const accounts = useAccountOptions();
  const taxCodes = useTaxCodes();
  const createBill = useCreateVendorBill();

  const [partnerId, setPartnerId] = useState("");
  const [billDate, setBillDate] = useState(today());
  const [dueDate, setDueDate] = useState(today());
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [apAccountId, setApAccountId] = useState("");
  const [externalRef, setExternalRef] = useState("");
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState<VendorBillLineCreate[]>([{ account_id: "", net_amount: "" }]);
  const [error, setError] = useState<string | null>(null);

  const validLines = lines.filter((line) => line.account_id && (Number(line.net_amount) || 0) > 0);
  const canSubmit = Boolean(partnerId && apAccountId && validLines.length > 0);

  const submit = async () => {
    setError(null);
    try {
      const vendor = vendors.data?.items.find((v) => v.id === partnerId);
      const bill = await createBill.mutateAsync({
        partner_id: partnerId,
        partner_name: vendor?.name ?? "",
        bill_date: billDate,
        due_date: dueDate,
        currency_code: currencyCode,
        ap_account_id: apAccountId,
        bill_external_ref: externalRef || null,
        description: description || null,
        lines: validLines,
      });
      void navigate({ to: "/finance/vendor-bills/$billId", params: { billId: bill.id } });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to create the bill.");
    }
  };

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-xl font-semibold text-ink">New vendor bill</h1>
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
            onChange={(event) => setPartnerId(event.target.value)}
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
          <label htmlFor="ap-account" className="mb-1 block text-xs font-medium text-ink-muted">
            AP account
          </label>
          <select
            id="ap-account"
            value={apAccountId}
            onChange={(event) => setApAccountId(event.target.value)}
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
            Vendor's reference
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
          <label htmlFor="bill-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Bill date
          </label>
          <input
            id="bill-date"
            type="date"
            value={billDate}
            onChange={(event) => setBillDate(event.target.value)}
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
        <BillLinesEditor
          lines={lines}
          accounts={accounts.data?.items ?? []}
          taxCodes={taxCodes.data?.items ?? []}
          onChange={setLines}
        />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createBill.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createBill.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
