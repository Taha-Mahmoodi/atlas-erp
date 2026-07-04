/**
 * Create an RFQ (STRUCTURE §4). No edit path — like vendor bills, RFQs are create-then-work
 * only per the backend surface (no PATCH endpoint); lines gain pricing later via record-quote.
 */

import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import { RfqLinesEditor } from "@/modules/procurement/components/RfqLinesEditor";
import { useCreateRfq, useVendorOptions } from "@/modules/procurement/hooks";
import type { RfqLineCreate } from "@/modules/procurement/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

export function RfqFormPage() {
  const navigate = useNavigate();
  const vendors = useVendorOptions();
  const items = useItemOptions();
  const uoms = useUomOptions();
  const createRfq = useCreateRfq();

  const [vendorId, setVendorId] = useState("");
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [validUntil, setValidUntil] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<RfqLineCreate[]>([{ item_id: "", quantity: "", uom_id: "" }]);
  const [error, setError] = useState<string | null>(null);

  const validLines = lines.filter((line) => line.item_id && line.uom_id && (Number(line.quantity) || 0) > 0);
  const canSubmit = Boolean(vendorId) && validLines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const rfq = await createRfq.mutateAsync({
        vendor_id: vendorId,
        currency_code: currencyCode,
        valid_until: validUntil || null,
        notes: notes || null,
        lines: validLines,
      });
      void navigate({ to: "/procurement/rfqs/$rfqId", params: { rfqId: rfq.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the RFQ."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">New RFQ</h1>
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
            value={vendorId}
            onChange={(event) => setVendorId(event.target.value)}
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
        <div>
          <label htmlFor="valid-until" className="mb-1 block text-xs font-medium text-ink-muted">
            Valid until
          </label>
          <input
            id="valid-until"
            type="date"
            value={validUntil}
            onChange={(event) => setValidUntil(event.target.value)}
            className={CONTROL}
          />
        </div>
        <div className="col-span-3">
          <label htmlFor="notes" className="mb-1 block text-xs font-medium text-ink-muted">
            Notes
          </label>
          <input
            id="notes"
            type="text"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            className={CONTROL}
          />
        </div>
      </div>

      <div className="mt-6">
        <RfqLinesEditor lines={lines} items={items.data?.items ?? []} uoms={uoms.data?.items ?? []} onChange={setLines} />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || createRfq.isPending}
        className="mt-6 rounded-control bg-primary px-4 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong disabled:cursor-not-allowed disabled:opacity-45"
      >
        {createRfq.isPending ? "Creating…" : "Create draft"}
      </button>
    </div>
  );
}
