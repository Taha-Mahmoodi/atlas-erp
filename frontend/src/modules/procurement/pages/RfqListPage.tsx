/**
 * RFQs list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useRfqs, useVendorLookup } from "@/modules/procurement/hooks";
import type { Rfq, RfqStatus } from "@/modules/procurement/types";

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
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/procurement" className="hover:underline">
            Procurement
          </Link>{" "}
          / <span className="text-ink">RFQs</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">RFQs</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/procurement/rfqs/new"
                className="btn-ink"
              >
                New RFQ
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
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
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={rfqs.hasNextPage}
          onLoadMore={() => void rfqs.fetchNextPage()}
          loadingMore={rfqs.isFetchingNextPage}
          label="RFQs"
        />
      </div>
    </div>
  );
}
