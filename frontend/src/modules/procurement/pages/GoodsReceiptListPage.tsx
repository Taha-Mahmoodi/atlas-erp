/**
 * Goods receipts list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useGoodsReceipts, useVendorLookup } from "@/modules/procurement/hooks";
import type { GoodsReceipt, GoodsReceiptStatus } from "@/modules/procurement/types";

const STATUS_TONE: Record<GoodsReceiptStatus, string> = {
  DRAFT: "bg-warn-tint text-warn",
  POSTED: "bg-success-tint text-success",
  CANCELLED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: GoodsReceiptStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

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
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Goods Receipts</h1>
        {canManage && (
          <Link
            to="/procurement/goods-receipts/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New goods receipt
          </Link>
        )}
      </div>

      <div className="mt-4">
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
          hasMore={receipts.hasNextPage}
          onLoadMore={() => void receipts.fetchNextPage()}
          loadingMore={receipts.isFetchingNextPage}
          label="Goods receipts"
        />
      </div>
    </div>
  );
}
