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
import { useRoutings } from "@/modules/manufacturing/hooks";
import type { Routing, RoutingStatus } from "@/modules/manufacturing/types";

const STATUS_TONE: Record<RoutingStatus, string> = {
  DRAFT: "bg-panel text-ink-muted",
  ACTIVE: "bg-success-tint text-success",
  INACTIVE: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: RoutingStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

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
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Routings</h1>
        {canManage && (
          <Link
            to="/manufacturing/routings/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
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
