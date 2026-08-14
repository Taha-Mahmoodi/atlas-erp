/**
 * Routings list (STRUCTURE §4). A routing's identity is (item_id, version), the BOM twin —
 * the list shows both since there's no separate code. Filterable by status, keyset-paginated
 * (D-014).
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { useItemLookup } from "@/modules/inventory/hooks";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useRoutings } from "@/modules/manufacturing/hooks";
import type { Routing, RoutingStatus } from "@/modules/manufacturing/types";

export function RoutingListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("manufacturing.routing.manage");
  const [status, setStatus] = useState<RoutingStatus | "">("");

  const routings = useRoutings(status ? { status } : {});
  const items = useItemLookup();
  const rows = routings.data?.pages.flatMap((page) => page.items) ?? [];

  const itemLabel = (id: string) => {
    const item = items.data?.items.find((i) => i.id === id);
    return item ? `${item.item_code} — ${item.name}` : id;
  };

  const columns: DataGridColumn<Routing>[] = [
    { key: "item_id", header: "Item", render: (row) => itemLabel(row.item_id) },
    { key: "version", header: "Version", render: (row) => row.version, width: "100px" },
    { key: "name", header: "Name", render: (row) => row.name },
    {
      key: "is_default",
      header: "Default",
      render: (row) => (row.is_default ? "Yes" : "—"),
      width: "90px",
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Routings</h1>
        {canManage && (
          <Link
            to="/manufacturing/routings/new"
            className="btn-ink"
          >
            New routing
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as RoutingStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="DRAFT">Draft</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) =>
            void navigate({ to: "/manufacturing/routings/$routingId", params: { routingId: row.id } })
          }
          loading={routings.isPending}
          emptyMessage="No routings yet."
          hasMore={routings.hasNextPage}
          onLoadMore={() => void routings.fetchNextPage()}
          loadingMore={routings.isFetchingNextPage}
          label="Routings"
        />
      </div>
    </div>
  );
}
