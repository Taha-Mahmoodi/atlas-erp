/**
 * The check (STRUCTURE §4): its lines, its total, and the one action it may take next.
 *
 * The total is labelled PRE-TAX because it is (docs/modules/hospitality.md §6 limit 3): Phase 19
 * posts no tax and takes no payment, while the hospitality template seeds F&B tax codes — so a
 * screen presenting this number as the amount due would understate it. Saying so is the honest
 * fix until the folio lands; hiding it is not.
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatDateTime, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { StatusPill } from "@/components/StatusPill";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { TicketLinesEditor } from "@/modules/hospitality/components/TicketLinesEditor";
import { TicketStatusFlow } from "@/modules/hospitality/components/TicketStatusFlow";
import { useTicket, useTicketLines } from "@/modules/hospitality/hooks";

export function TicketDetailPage() {
  const { ticketId } = useParams({ strict: false });
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hospitality.ticket.manage");

  const ticket = useTicket(ticketId);
  const lines = useTicketLines(ticketId);
  const currencyCode = useFunctionalCurrency().data ?? "—";
  const [error, setError] = useState<string | null>(null);

  if (ticket.isPending || !ticket.data) {
    return <p className="text-[13px] text-ink-muted">Loading…</p>;
  }
  const data = ticket.data;

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality/tickets" className="hover:underline">
            Tickets
          </Link>{" "}
          / <span className="text-ink">{data.ticket_number}</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">
            {data.ticket_number}
          </h1>
          <TicketStatusFlow ticket={data} onError={setError} />
        </div>
      </header>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Status</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            <StatusPill status={data.status} />
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Table</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.table_code ?? "—"}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Guests</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums text-ink">{data.guest_count ?? "—"}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Service date</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{formatDate(data.opened_date)}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Fired</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {data.fired_at ? formatDateTime(data.fired_at) : "—"}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Settled</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            {data.settled_at ? formatDateTime(data.settled_at) : "—"}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Total (pre-tax)</dt>
          <dd className="mt-1.5 text-[13px] tabular-nums font-medium text-ink">
            {formatMoney(data.total_amount, currencyCode)}
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Notes</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{data.notes ?? "—"}</dd>
        </div>
      </dl>

      <TicketLinesEditor
        ticketId={data.id}
        lines={lines.data ?? []}
        currencyCode={currencyCode}
        editable={data.status === "OPEN" && canManage}
      />
    </div>
  );
}
