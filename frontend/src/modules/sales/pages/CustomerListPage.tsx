/**
 * Customers list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens edit. Mirrors procurement's VendorListPage.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomers } from "@/modules/sales/hooks";
import type { Customer, CustomerStatus } from "@/modules/sales/types";

const COLUMNS: DataGridColumn<Customer>[] = [
  { key: "customer_code", header: "Code", render: (row) => row.customer_code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "default_currency_code", header: "Currency", render: (row) => row.default_currency_code, width: "100px" },
  { key: "payment_terms_days", header: "Terms", render: (row) => `NET ${row.payment_terms_days}`, width: "100px" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
];

export function CustomerListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.customer.manage");
  const [status, setStatus] = useState<CustomerStatus | "">("");

  const customers = useCustomers(status ? { status } : {});
  const rows = customers.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Customers</h1>
        {canManage && (
          <Link
            to="/sales/customers/new"
            className="btn-ink"
          >
            New customer
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as CustomerStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="BLOCKED">Blocked</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/customers/$customerId", params: { customerId: row.id } })}
          loading={customers.isPending}
          emptyMessage="No customers yet."
          hasMore={customers.hasNextPage}
          onLoadMore={() => void customers.fetchNextPage()}
          loadingMore={customers.isFetchingNextPage}
          label="Customers"
        />
      </div>
    </div>
  );
}
