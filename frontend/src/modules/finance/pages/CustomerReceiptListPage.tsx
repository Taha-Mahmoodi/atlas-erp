/**
 * Customer receipts list (STRUCTURE §4) — the AR mirror of VendorPaymentListPage. Read-only —
 * the backend exposes no GET /customer-receipts/{id}, so rows aren't clickable; a receipt's
 * allocations are only ever shown once, right after creation (CustomerReceiptFormPage's
 * success panel).
 */

import { Link } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomerReceipts } from "@/modules/finance/hooks";
import type { CustomerReceipt } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<CustomerReceipt>[] = [
  { key: "receipt_number", header: "Receipt #", render: (row) => row.receipt_number ?? "—", width: "150px" },
  { key: "partner_name", header: "Customer", render: (row) => row.partner_name },
  { key: "receipt_date", header: "Date", render: (row) => formatDate(row.receipt_date), width: "120px" },
  {
    key: "amount",
    header: "Amount",
    align: "right",
    render: (row) => formatMoney(row.amount, row.currency_code),
    width: "130px",
  },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
];

export function CustomerReceiptListPage() {
  const me = useMe();
  const canCollect = (me.data?.permissions ?? []).includes("finance.ar.collect");
  const receipts = useCustomerReceipts();
  const rows = receipts.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Customer Receipts</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Customer Receipts</h1>
          <div className="flex items-center gap-2.5">
            {canCollect && (
              <Link
                to="/finance/customer-receipts/new"
                className="btn-ink"
              >
                New receipt
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          loading={receipts.isPending}
          emptyMessage="No customer receipts yet."
          hasMore={receipts.hasNextPage}
          onLoadMore={() => void receipts.fetchNextPage()}
          loadingMore={receipts.isFetchingNextPage}
          label="Customer receipts"
        />
      </div>
    </div>
  );
}
