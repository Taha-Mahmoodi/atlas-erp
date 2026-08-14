/**
 * Items list (STRUCTURE §4). Filterable by type/active, keyset-paginated (D-014); row click
 * opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useItems } from "@/modules/inventory/hooks";
import type { Item, ItemType } from "@/modules/inventory/types";
import { StatusPill } from "@/components/StatusPill";

const COLUMNS: DataGridColumn<Item>[] = [
  { key: "item_code", header: "Item #", render: (row) => row.item_code, width: "130px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "item_type", header: "Type", render: (row) => row.item_type.replace("_", " "), width: "130px" },
  { key: "costing_method", header: "Costing", render: (row) => row.costing_method.replace("_", " "), width: "150px" },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (
      <StatusPill status={row.is_active ? "ACTIVE" : "INACTIVE"} />
    ),
    width: "100px",
  },
];

export function ItemListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.item.manage");
  const [itemType, setItemType] = useState<ItemType | "">("");

  const items = useItems(itemType ? { item_type: itemType } : {});
  const rows = items.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Items</h1>
        {canManage && (
          <Link
            to="/inventory/items/new"
            className="btn-ink"
          >
            New item
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={itemType}
          onChange={(event) => setItemType(event.target.value as ItemType | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All types</option>
          <option value="STOCKED">Stocked</option>
          <option value="NON_STOCKED">Non-stocked</option>
          <option value="SERVICE">Service</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/items/$itemId", params: { itemId: row.id } })}
          loading={items.isPending}
          emptyMessage="No items yet."
          hasMore={items.hasNextPage}
          onLoadMore={() => void items.fetchNextPage()}
          loadingMore={items.isFetchingNextPage}
          label="Items"
        />
      </div>
    </div>
  );
}
