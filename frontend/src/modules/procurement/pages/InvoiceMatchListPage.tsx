/**
 * Invoice matches list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useInvoiceMatches, useVendorLookup } from "@/modules/procurement/hooks";
import type { InvoiceMatch, MatchStatus } from "@/modules/procurement/types";

export function InvoiceMatchListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.invoice_match.manage");
  const [status, setStatus] = useState<MatchStatus | "">("");

  const matches = useInvoiceMatches(status ? { status } : {});
  const vendors = useVendorLookup();
  const rows = matches.data?.pages.flatMap((page) => page.items) ?? [];

  const vendorLabel = (id: string) => {
    const vendor = vendors.data?.items.find((v) => v.id === id);
    return vendor ? `${vendor.vendor_code} — ${vendor.name}` : id;
  };

  const columns: DataGridColumn<InvoiceMatch>[] = [
    { key: "match_number", header: "Match #", render: (row) => row.match_number, width: "140px" },
    { key: "vendor_id", header: "Vendor", render: (row) => vendorLabel(row.vendor_id) },
    { key: "vendor_invoice_ref", header: "Vendor invoice ref", render: (row) => row.vendor_invoice_ref ?? "—" },
    {
      key: "total_amount",
      header: "Total",
      align: "right",
      render: (row) => formatMoney(row.total_amount, row.currency_code),
      width: "140px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Invoice Matches</h1>
        {canManage && (
          <Link
            to="/procurement/invoice-matches/new"
            className="btn-ink"
          >
            New match
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as MatchStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="MATCHED">Matched</option>
          <option value="EXCEPTION">Exception</option>
          <option value="POSTED">Posted</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/procurement/invoice-matches/$invoiceMatchId", params: { invoiceMatchId: row.id } })}
          loading={matches.isPending}
          emptyMessage="No invoice matches yet."
          hasMore={matches.hasNextPage}
          onLoadMore={() => void matches.fetchNextPage()}
          loadingMore={matches.isFetchingNextPage}
          label="Invoice matches"
        />
      </div>
    </div>
  );
}
