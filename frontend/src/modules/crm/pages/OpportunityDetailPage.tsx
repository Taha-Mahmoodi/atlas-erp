/**
 * The opportunity workbench (STRUCTURE §4): facts + expected-product lines, edit while open,
 * and the convert-to-customer+quote action (distinct `crm.opportunity.convert` permission,
 * D-057) which navigates straight to the created sales quote. Stage moves live on the board.
 */

import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate, formatMoney, formatPercent, formatQuantity } from "@/lib/format";
import { useMe } from "@/lib/session";
import { ActivityTimeline } from "@/modules/crm/components/ActivityTimeline";
import { useConvertOpportunity, useOpportunity } from "@/modules/crm/hooks";
import { useItemLookup } from "@/modules/inventory/hooks";
import { StatusPill } from "@/components/StatusPill";

export function OpportunityDetailPage() {
  const { opportunityId } = useParams({ strict: false });
  const navigate = useNavigate();
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canManage = permissions.includes("crm.opportunity.manage");
  const canConvert = permissions.includes("crm.opportunity.convert");
  const canManageActivities = permissions.includes("crm.activity.manage");

  const opportunity = useOpportunity(opportunityId);
  const convert = useConvertOpportunity(opportunityId ?? "");
  const items = useItemLookup();
  const [error, setError] = useState<string | null>(null);

  if (opportunity.isPending || !opportunity.data) {
    return <p className="text-sm text-ink-muted">Loading…</p>;
  }
  const data = opportunity.data;
  const isOpen = data.stage !== "WON" && data.stage !== "LOST";

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((entry) => entry.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  const doConvert = async () => {
    setError(null);
    try {
      const converted = await convert.mutateAsync();
      if (converted.converted_quote_id) {
        void navigate({ to: "/sales/quotes/$quoteId", params: { quoteId: converted.converted_quote_id } });
      }
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to convert the opportunity."));
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {data.opportunity_number} — {data.name}
          <StatusPill status={data.stage} />
        </h1>
        <div className="flex gap-2">
          {isOpen && canManage && (
            <Link
              to="/crm/opportunities/$opportunityId/edit"
              params={{ opportunityId: data.id }}
              className="btn-chip"
            >
              Edit
            </Link>
          )}
          {isOpen && canConvert && (
            <button
              type="button"
              onClick={() => void doConvert()}
              disabled={convert.isPending}
              className="btn-ink"
            >
              {convert.isPending ? "Converting…" : "Convert to customer + quote"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      {data.converted_quote_id && (
        <p className="mt-4 rounded-control bg-success-tint px-3 py-2 text-xs text-success">
          Won and converted —{" "}
          <Link to="/sales/quotes/$quoteId" params={{ quoteId: data.converted_quote_id }} className="underline">
            view the quote
          </Link>
          {data.converted_customer_id && (
            <>
              {" · "}
              <Link
                to="/sales/customers/$customerId"
                params={{ customerId: data.converted_customer_id }}
                className="underline"
              >
                view the customer
              </Link>
            </>
          )}
          .
        </p>
      )}

      <dl className="mt-6 grid grid-cols-4 gap-4 text-sm">
        <div>
          <dt className="text-xs text-ink-muted">Company</dt>
          <dd className="text-ink">{data.company_name}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Contact</dt>
          <dd className="text-ink">{data.contact_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Estimated value</dt>
          <dd className="text-ink tabular-nums">{formatMoney(data.estimated_value, data.currency_code)}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Probability</dt>
          <dd className="text-ink tabular-nums">
            {data.probability_percent !== null ? formatPercent(data.probability_percent) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Expected close</dt>
          <dd className="text-ink">
            {data.expected_close_date ? formatDate(data.expected_close_date) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-muted">Source lead</dt>
          <dd className="text-ink">
            {data.source_lead_id ? (
              <Link to="/crm/leads/$leadId" params={{ leadId: data.source_lead_id }} className="text-primary underline">
                View lead
              </Link>
            ) : (
              "—"
            )}
          </dd>
        </div>
        {data.notes && (
          <div className="col-span-2">
            <dt className="text-xs text-ink-muted">Notes</dt>
            <dd className="text-ink">{data.notes}</dd>
          </div>
        )}
      </dl>

      {data.lines.length > 0 && (
        <table className="mt-6 w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line text-left mono-caps text-ink-muted">
              <th className="py-2 pr-2">Item</th>
              <th className="py-2 pr-2">Description</th>
              <th className="py-2 pr-2 text-right">Quantity</th>
              <th className="py-2 pr-2 text-right">Est. unit price</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((line) => (
              <tr key={line.id} className="border-b border-line last:border-b-0">
                <td className="py-1.5 pr-2 text-ink">{itemLabel(line.item_id)}</td>
                <td className="py-1.5 pr-2 text-ink-muted">{line.description ?? "—"}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{formatQuantity(line.quantity)}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">
                  {formatMoney(line.estimated_unit_price, data.currency_code)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mt-8">
        <ActivityTimeline parent={{ opportunity_id: data.id }} canManage={canManageActivities} />
      </div>
    </div>
  );
}
