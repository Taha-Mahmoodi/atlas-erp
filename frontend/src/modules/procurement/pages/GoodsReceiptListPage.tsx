/**
 * Goods receipts list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useGoodsReceipts, useVendorLookup } from "@/modules/procurement/hooks";
import type { GoodsReceipt, GoodsReceiptStatus } from "@/modules/procurement/types";

export function GoodsReceiptListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.goods_receipt.manage");
  const [status, setStatus] = useState<GoodsReceiptStatus | "">("");

  const receipts = useGoodsReceipts(status ? { status } : {});
  const vendors = useVendorLookup();
  const rows = receipts.data?.pages.flatMap((page) => page.items) ?? [];

  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const columns: DataGridColumn<GoodsReceipt>[] = [
    { key: "gr_number", header: "GR #", render: (row) => row.gr_number, width: "140px" },
    { key: "vendor_id", header: "Vendor", render: (row) => vendorLabel(row.vendor_id) },
    { key: "receipt_date", header: "Receipt date", render: (row) => row.receipt_date, width: "120px" },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/procurement" className="hover:underline">
            Procurement
          </Link>{" "}
          / <span className="text-ink">Goods Receipts</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Goods Receipts</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/procurement/goods-receipts/new"
                className="btn-ink"
              >
                New goods receipt
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as GoodsReceiptStatus | "")}
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
          onRowClick={(row) => void navigate({ to: "/procurement/goods-receipts/$goodsReceiptId", params: { goodsReceiptId: row.id } })}
          loading={receipts.isPending}
          emptyMessage="No goods receipts yet."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={receipts.hasNextPage}
          onLoadMore={() => void receipts.fetchNextPage()}
          loadingMore={receipts.isFetchingNextPage}
          label="Goods receipts"
        />
      </div>
    </div>
  );
}
