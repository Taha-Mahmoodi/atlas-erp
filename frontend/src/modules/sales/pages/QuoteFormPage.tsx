/**
 * Create or edit a quote (STRUCTURE §4). Edit mode via `/sales/quotes/$quoteId/edit`; create
 * via `/sales/quotes/new`. Only a DRAFT quote is editable (enforced server-side) — PATCH
 * replaces the whole line set wholesale, so this page always submits the full current line
 * array, never a diff (mirrors procurement's RequisitionFormPage).
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useItemOptions, useUomOptions } from "@/modules/inventory/hooks";
import { QuoteLinesEditor } from "@/modules/sales/components/QuoteLinesEditor";
import { useCreateQuote, useCustomerOptions, useQuote, useUpdateQuote } from "@/modules/sales/hooks";
import type { QuoteLineCreate } from "@/modules/sales/types";

const CONTROL =
  "w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-ink-faint";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function QuoteFormPage() {
  const { quoteId } = useParams({ strict: false });
  const isEdit = quoteId !== undefined;
  const navigate = useNavigate();

  const quote = useQuote(quoteId);
  const customers = useCustomerOptions();
  const items = useItemOptions();
  const uoms = useUomOptions();
  const createQuote = useCreateQuote();
  const updateQuote = useUpdateQuote(quoteId ?? "");

  const [customerId, setCustomerId] = useState("");
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [quoteDate, setQuoteDate] = useState(today());
  const [validUntil, setValidUntil] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState<QuoteLineCreate[]>([{ item_id: "", quantity: "", uom_id: "" }]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (quote.data) {
      setCustomerId(quote.data.customer_id);
      setCurrencyCode(quote.data.currency_code);
      setQuoteDate(quote.data.quote_date);
      setValidUntil(quote.data.valid_until ?? "");
      setNotes(quote.data.notes ?? "");
      setLines(
        quote.data.lines.map((line) => ({
          item_id: line.item_id,
          description: line.description,
          quantity: line.quantity,
          uom_id: line.uom_id,
          unit_price: line.unit_price,
          discount_type: line.discount_type,
          discount_value: line.discount_value,
        })),
      );
    }
  }, [quote.data]);

  const validLines = lines.filter((line) => line.item_id && line.uom_id && (Number(line.quantity) || 0) > 0);
  const canSubmit = Boolean(customerId) && validLines.length > 0;

  const submit = async () => {
    setError(null);
    try {
      const shared = {
        currency_code: currencyCode,
        quote_date: quoteDate || null,
        valid_until: validUntil || null,
        notes: notes || null,
        lines: validLines,
      };
      if (isEdit) {
        await updateQuote.mutateAsync(shared);
        void navigate({ to: "/sales/quotes/$quoteId", params: { quoteId } });
      } else {
        const created = await createQuote.mutateAsync({ ...shared, customer_id: customerId });
        void navigate({ to: "/sales/quotes/$quoteId", params: { quoteId: created.id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to save the quote."));
    }
  };

  const busy = createQuote.isPending || updateQuote.isPending;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales/quotes">Quotes</Link> /{" "}
          <span className="text-ink">{isEdit ? "Edit quote" : "New quote"}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{isEdit ? "Edit quote" : "New quote"}</h1>
        </div>
      </header>
      {error && (
        <p role="alert" className="mb-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6 grid grid-cols-4 gap-4">
        <div>
          <label htmlFor="customer" className="mb-1 block text-xs font-medium text-ink-muted">
            Customer
          </label>
          <select
            id="customer"
            value={customerId}
            onChange={(event) => setCustomerId(event.target.value)}
            disabled={isEdit}
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
          <label htmlFor="quote-date" className="mb-1 block text-xs font-medium text-ink-muted">
            Quote date
          </label>
          <input
            id="quote-date"
            type="date"
            value={quoteDate}
            onChange={(event) => setQuoteDate(event.target.value)}
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
        <div className="col-span-4">
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
        <QuoteLinesEditor lines={lines} items={items.data?.items ?? []} uoms={uoms.data?.items ?? []} onChange={setLines} />
      </div>

      <button
        type="button"
        onClick={() => void submit()}
        disabled={!canSubmit || busy}
        className="mt-6 btn-ink"
      >
        {busy ? "Saving…" : isEdit ? "Save changes" : "Create draft"}
      </button>
    </div>
  );
}
