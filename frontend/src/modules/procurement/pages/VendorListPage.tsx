/**
 * Vendors list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useVendors } from "@/modules/procurement/hooks";
import type { Vendor, VendorStatus } from "@/modules/procurement/types";

const COLUMNS: DataGridColumn<Vendor>[] = [
  { key: "vendor_code", header: "Code", render: (row) => row.vendor_code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "default_currency_code", header: "Currency", render: (row) => row.default_currency_code, width: "100px" },
  { key: "payment_terms_days", header: "Terms", render: (row) => `NET ${row.payment_terms_days}`, width: "100px" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
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
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Vendors</h1>
        {canManage && (
          <Link
            to="/procurement/vendors/new"
            className="btn-ink"
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
