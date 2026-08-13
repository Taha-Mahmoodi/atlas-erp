/**
 * Returns (RMA) list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useCustomerOptions, useReturns } from "@/modules/sales/hooks";
import type { Return, ReturnStatus } from "@/modules/sales/types";

const STATUS_TONE: Record<ReturnStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  POSTED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: ReturnStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

export function ReturnListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.return.manage");
  const [status, setStatus] = useState<ReturnStatus | "">("");

  const returns = useReturns(status ? { status } : {});
  const customers = useCustomerOptions();
  const rows = returns.data?.pages.flatMap((page) => page.items) ?? [];

  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const columns: DataGridColumn<Return>[] = [
    { key: "return_number", header: "Return #", render: (row) => row.return_number, width: "140px" },
    { key: "customer_id", header: "Customer", render: (row) => customerLabel(row.customer_id) },
    { key: "reason", header: "Reason", render: (row) => row.reason ?? "—" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Returns</h1>
        {canManage && (
          <Link
            to="/sales/returns/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New return
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as ReturnStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="POSTED">Posted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/returns/$returnId", params: { returnId: row.id } })}
          loading={returns.isPending}
          emptyMessage="No returns yet."
          hasMore={returns.hasNextPage}
          onLoadMore={() => void returns.fetchNextPage()}
          loadingMore={returns.isFetchingNextPage}
          label="Returns"
        />
      </div>
    </div>
  );
}
