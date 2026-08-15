/**
 * The floor's checks (STRUCTURE §4): keyset-paginated (D-014), newest service date first,
 * filtered by the two things a floor plan actually filters on — status and service date.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { humanizeStatus, StatusPill } from "@/components/StatusPill";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { TICKET_FLOW } from "@/modules/hospitality/components/ticketFlow";
import { useTickets } from "@/modules/hospitality/hooks";
import type { OrderTicket, OrderTicketStatus } from "@/modules/hospitality/types";

export function TicketListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hospitality.ticket.manage");
  const [status, setStatus] = useState<OrderTicketStatus | "">("");
  const [openedOn, setOpenedOn] = useState("");

  const tickets = useTickets({
    ...(status ? { status } : {}),
    ...(openedOn ? { opened_on: openedOn } : {}),
  });
  const rows = tickets.data?.pages.flatMap((page) => page.items) ?? [];
  // A ticket carries no currency of its own (D-019) — the tenant's functional currency is the
  // only one it can be in.
  const currencyCode = useFunctionalCurrency().data ?? "—";

  const columns: DataGridColumn<OrderTicket>[] = [
    { key: "ticket_number", header: "Ticket", width: "150px", render: (row) => row.ticket_number },
    { key: "table_code", header: "Table", width: "100px", render: (row) => row.table_code ?? "—" },
    {
      key: "guest_count",
      header: "Guests",
      align: "right",
      width: "90px",
      render: (row) => row.guest_count ?? "—",
    },
    {
      key: "status",
      header: "Status",
      width: "150px",
      render: (row) => <StatusPill status={row.status} />,
    },
    {
      key: "total_amount",
      header: "Total (pre-tax)",
      align: "right",
      width: "160px",
      render: (row) => formatMoney(row.total_amount, currencyCode),
    },
    {
      key: "opened_date",
      header: "Opened",
      width: "140px",
      render: (row) => formatDate(row.opened_date),
    },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality" className="hover:underline">
            Hospitality
          </Link>{" "}
          / <span className="text-ink">Tickets</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Tickets</h1>
          {canManage && (
            <Link to="/hospitality/tickets/new" className="btn-ink">
              New ticket
            </Link>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Status"
          value={status}
          onChange={(event) => setStatus(event.target.value as OrderTicketStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          {TICKET_FLOW.map((value) => (
            <option key={value} value={value}>
              {humanizeStatus(value)}
            </option>
          ))}
        </select>
        <input
          aria-label="Service date"
          type="date"
          value={openedOn}
          onChange={(event) => setOpenedOn(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        />
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) =>
            void navigate({
              to: "/hospitality/tickets/$ticketId",
              params: { ticketId: row.id },
            })
          }
          loading={tickets.isPending}
          emptyMessage="No checks yet — open one when a table is seated."
          isFiltered={Boolean(status || openedOn)}
          onClearFilters={() => {
            setStatus("");
            setOpenedOn("");
          }}
          hasMore={tickets.hasNextPage}
          onLoadMore={() => void tickets.fetchNextPage()}
          loadingMore={tickets.isFetchingNextPage}
          label="Order tickets"
        />
      </div>
    </div>
  );
}
