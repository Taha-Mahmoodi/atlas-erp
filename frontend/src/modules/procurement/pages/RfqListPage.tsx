/**
 * RFQs list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useRfqs, useVendorLookup } from "@/modules/procurement/hooks";
import type { Rfq, RfqStatus } from "@/modules/procurement/types";

const STATUS_TONE: Record<RfqStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  SENT: "bg-warn-tint text-warn",
  QUOTED: "bg-primary-tint text-primary",
  CLOSED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: RfqStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

export function RfqListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.rfq.manage");
  const [status, setStatus] = useState<RfqStatus | "">("");

  const rfqs = useRfqs(status ? { status } : {});
  const vendors = useVendorLookup();
  const rows = rfqs.data?.pages.flatMap((page) => page.items) ?? [];

  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const columns: DataGridColumn<Rfq>[] = [
    { key: "rfq_number", header: "RFQ #", render: (row) => row.rfq_number, width: "140px" },
    { key: "vendor_id", header: "Vendor", render: (row) => vendorLabel(row.vendor_id) },
    { key: "valid_until", header: "Valid until", render: (row) => row.valid_until ?? "—", width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">RFQs</h1>
        {canManage && (
          <Link
            to="/procurement/rfqs/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New RFQ
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as RfqStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="SENT">Sent</option>
          <option value="QUOTED">Quoted</option>
          <option value="CLOSED">Closed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/procurement/rfqs/$rfqId", params: { rfqId: row.id } })}
          loading={rfqs.isPending}
          emptyMessage="No RFQs yet."
          hasMore={rfqs.hasNextPage}
          onLoadMore={() => void rfqs.fetchNextPage()}
          loadingMore={rfqs.isFetchingNextPage}
          label="RFQs"
        />
      </div>
    </div>
  );
}
