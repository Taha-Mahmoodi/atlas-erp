/**
 * Vendor bills list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row
 * click opens the bill (Post action lives on the detail page).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useVendorBills } from "@/modules/finance/hooks";
import type { BillStatus, VendorBill } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<VendorBill>[] = [
  { key: "bill_number", header: "Bill #", render: (row) => row.bill_number ?? "(draft)", width: "150px" },
  { key: "partner_name", header: "Vendor", render: (row) => row.partner_name },
  { key: "due_date", header: "Due date", render: (row) => formatDate(row.due_date), width: "120px" },
  {
    key: "gross_amount",
    header: "Gross",
    align: "right",
    render: (row) => formatMoney(row.gross_amount, row.currency_code),
    width: "130px",
  },
  {
    key: "open_amount",
    header: "Open",
    align: "right",
    render: (row) => formatMoney(row.open_amount, row.currency_code),
    width: "130px",
  },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "120px" },
];

export function VendorBillListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.ap.manage");
  const [status, setStatus] = useState<BillStatus | "">("");

  const bills = useVendorBills(status ? { status } : {});
  const rows = bills.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Vendor Bills</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Vendor Bills</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/finance/vendor-bills/new"
                className="btn-ink"
              >
                New bill
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as BillStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="POSTED">Posted</option>
          <option value="PARTIALLY_PAID">Partially paid</option>
          <option value="PAID">Paid</option>
          <option value="REVERSED">Reversed</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/vendor-bills/$billId", params: { billId: row.id } })}
          loading={bills.isPending}
          emptyMessage="No vendor bills yet."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={bills.hasNextPage}
          onLoadMore={() => void bills.fetchNextPage()}
          loadingMore={bills.isFetchingNextPage}
          label="Vendor bills"
        />
      </div>
    </div>
  );
}
