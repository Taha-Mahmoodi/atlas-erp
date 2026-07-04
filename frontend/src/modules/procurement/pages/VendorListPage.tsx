/**
 * Vendors list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useVendors } from "@/modules/procurement/hooks";
import type { Vendor, VendorStatus } from "@/modules/procurement/types";

const STATUS_TONE: Record<VendorStatus, string> = {
  ACTIVE: "bg-success-tint text-success",
  BLOCKED: "bg-danger-tint text-danger",
  INACTIVE: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: VendorStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

const COLUMNS: DataGridColumn<Vendor>[] = [
  { key: "vendor_code", header: "Code", render: (row) => row.vendor_code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "default_currency_code", header: "Currency", render: (row) => row.default_currency_code, width: "100px" },
  { key: "payment_terms_days", header: "Terms", render: (row) => `NET ${row.payment_terms_days}`, width: "100px" },
  { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
];

export function VendorListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.vendor.manage");
  const [status, setStatus] = useState<VendorStatus | "">("");

  const vendors = useVendors(status ? { status } : {});
  const rows = vendors.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Vendors</h1>
        {canManage && (
          <Link
            to="/procurement/vendors/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New vendor
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as VendorStatus | "")}
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
          onRowClick={(row) => void navigate({ to: "/procurement/vendors/$vendorId", params: { vendorId: row.id } })}
          loading={vendors.isPending}
          emptyMessage="No vendors yet."
          hasMore={vendors.hasNextPage}
          onLoadMore={() => void vendors.fetchNextPage()}
          loadingMore={vendors.isFetchingNextPage}
          label="Vendors"
        />
      </div>
    </div>
  );
}
