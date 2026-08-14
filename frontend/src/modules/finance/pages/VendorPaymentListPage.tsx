/**
 * Vendor payments list (STRUCTURE §4). Read-only — the backend exposes no
 * GET /vendor-payments/{id}, so rows aren't clickable; a payment's allocations are only ever
 * shown once, right after creation (VendorPaymentFormPage's success panel).
 */

import { Link } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useVendorPayments } from "@/modules/finance/hooks";
import type { VendorPayment } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<VendorPayment>[] = [
  { key: "payment_number", header: "Payment #", render: (row) => row.payment_number ?? "—", width: "150px" },
  { key: "partner_name", header: "Vendor", render: (row) => row.partner_name },
  { key: "payment_date", header: "Date", render: (row) => formatDate(row.payment_date), width: "120px" },
  {
    key: "amount",
    header: "Amount",
    align: "right",
    render: (row) => formatMoney(row.amount, row.currency_code),
    width: "130px",
  },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
];

export function VendorPaymentListPage() {
  const me = useMe();
  const canPay = (me.data?.permissions ?? []).includes("finance.ap.pay");
  const payments = useVendorPayments();
  const rows = payments.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Vendor Payments</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Vendor Payments</h1>
          <div className="flex items-center gap-2.5">
            {canPay && (
              <Link
                to="/finance/vendor-payments/new"
                className="btn-ink"
              >
                New payment
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
          loading={payments.isPending}
          emptyMessage="No vendor payments yet."
          hasMore={payments.hasNextPage}
          onLoadMore={() => void payments.fetchNextPage()}
          loadingMore={payments.isFetchingNextPage}
          label="Vendor payments"
        />
      </div>
    </div>
  );
}
