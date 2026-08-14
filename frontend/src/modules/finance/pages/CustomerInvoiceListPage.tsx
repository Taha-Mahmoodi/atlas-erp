/**
 * Customer invoices list (STRUCTURE §4) — the AR mirror of VendorBillListPage. Filterable by
 * status, keyset-paginated (D-014); row click opens the invoice (Post lives on the detail page).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useCustomerInvoices } from "@/modules/finance/hooks";
import type { CustomerInvoice, InvoiceStatus } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<CustomerInvoice>[] = [
  { key: "invoice_number", header: "Invoice #", render: (row) => row.invoice_number ?? "(draft)", width: "150px" },
  { key: "partner_name", header: "Customer", render: (row) => row.partner_name },
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

export function CustomerInvoiceListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.ar.manage");
  const [status, setStatus] = useState<InvoiceStatus | "">("");

  const invoices = useCustomerInvoices(status ? { status } : {});
  const rows = invoices.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Customer Invoices</h1>
        {canManage && (
          <Link
            to="/finance/customer-invoices/new"
            className="btn-ink"
          >
            New invoice
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as InvoiceStatus | "")}
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
          onRowClick={(row) => void navigate({ to: "/finance/customer-invoices/$invoiceId", params: { invoiceId: row.id } })}
          loading={invoices.isPending}
          emptyMessage="No customer invoices yet."
          hasMore={invoices.hasNextPage}
          onLoadMore={() => void invoices.fetchNextPage()}
          loadingMore={invoices.isFetchingNextPage}
          label="Customer invoices"
        />
      </div>
    </div>
  );
}
