/**
 * Billings list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014). A billing is a
 * wholly separate sales-side model from finance's CustomerInvoice — posting one creates a real
 * posted CustomerInvoice in finance via docflow, visible on finance's own AR pages.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useBillings, useCustomerOptions } from "@/modules/sales/hooks";
import type { Billing, BillingStatus } from "@/modules/sales/types";

export function BillingListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.billing.manage");
  const [status, setStatus] = useState<BillingStatus | "">("");

  const billings = useBillings(status ? { status } : {});
  const customers = useCustomerOptions();
  const rows = billings.data?.pages.flatMap((page) => page.items) ?? [];

  const customerLabel = (id: string) => {
    const customer = customers.data?.items.find((c) => c.id === id);
    return customer ? `${customer.customer_code} — ${customer.name}` : id;
  };

  const columns: DataGridColumn<Billing>[] = [
    { key: "billing_number", header: "Billing #", render: (row) => row.billing_number, width: "140px" },
    { key: "customer_id", header: "Customer", render: (row) => customerLabel(row.customer_id) },
    { key: "billing_date", header: "Billing date", render: (row) => row.billing_date, width: "120px" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/sales">Sales</Link> / <span className="text-ink">Billings</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Billings</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/sales/billings/new"
                className="btn-ink"
              >
                New billing
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as BillingStatus | "")}
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
          onRowClick={(row) => void navigate({ to: "/sales/billings/$billingId", params: { billingId: row.id } })}
          loading={billings.isPending}
          emptyMessage="No billings yet."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={billings.hasNextPage}
          onLoadMore={() => void billings.fetchNextPage()}
          loadingMore={billings.isFetchingNextPage}
          label="Billings"
        />
      </div>
    </div>
  );
}
