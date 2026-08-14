/**
 * Price lists list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens edit. Condition-style pricing: a header attribute match (currency + optional customer
 * group + date window) with one flat price per item on each list's lines.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { usePriceLists } from "@/modules/sales/hooks";
import type { PriceList, PriceListStatus } from "@/modules/sales/types";

const COLUMNS: DataGridColumn<PriceList>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "currency_code", header: "Currency", render: (row) => row.currency_code, width: "100px" },
  { key: "valid_from", header: "From", render: (row) => row.valid_from, width: "110px" },
  { key: "valid_to", header: "To", render: (row) => row.valid_to ?? "Open-ended", width: "110px" },
  { key: "priority", header: "Priority", align: "right", render: (row) => row.priority, width: "80px" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "100px" },
];

export function PriceListListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.pricelist.manage");
  const [status, setStatus] = useState<PriceListStatus | "">("");

  const priceLists = usePriceLists(status ? { status } : {});
  const rows = priceLists.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Price Lists</h1>
        {canManage && (
          <Link
            to="/sales/price-lists/new"
            className="btn-ink"
          >
            New price list
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as PriceListStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/price-lists/$priceListId", params: { priceListId: row.id } })}
          loading={priceLists.isPending}
          emptyMessage="No price lists yet."
          hasMore={priceLists.hasNextPage}
          onLoadMore={() => void priceLists.fetchNextPage()}
          loadingMore={priceLists.isFetchingNextPage}
          label="Price lists"
        />
      </div>
    </div>
  );
}
