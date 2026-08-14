/**
 * Quotes list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomerOptions, useQuotes } from "@/modules/sales/hooks";
import type { Quote, QuoteStatus } from "@/modules/sales/types";

export function QuoteListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.quote.manage");
  const [status, setStatus] = useState<QuoteStatus | "">("");

  const quotes = useQuotes(status ? { status } : {});
  const customers = useCustomerOptions();
  const rows = quotes.data?.pages.flatMap((page) => page.items) ?? [];

  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const columns: DataGridColumn<Quote>[] = [
    { key: "quote_number", header: "Quote #", render: (row) => row.quote_number, width: "140px" },
    { key: "customer_id", header: "Customer", render: (row) => customerLabel(row.customer_id) },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "valid_until", header: "Valid until", render: (row) => row.valid_until ?? "—", width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Quotes</h1>
        {canManage && (
          <Link
            to="/sales/quotes/new"
            className="btn-ink"
          >
            New quote
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as QuoteStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="SENT">Sent</option>
          <option value="ACCEPTED">Accepted</option>
          <option value="REJECTED">Rejected</option>
          <option value="CONVERTED">Converted</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="EXPIRED">Expired</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/quotes/$quoteId", params: { quoteId: row.id } })}
          loading={quotes.isPending}
          emptyMessage="No quotes yet."
          hasMore={quotes.hasNextPage}
          onLoadMore={() => void quotes.fetchNextPage()}
          loadingMore={quotes.isFetchingNextPage}
          label="Quotes"
        />
      </div>
    </div>
  );
}
