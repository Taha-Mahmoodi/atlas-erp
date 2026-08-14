/**
 * Item categories list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useItemCategories } from "@/modules/inventory/hooks";
import type { ItemCategory } from "@/modules/inventory/types";

const COLUMNS: DataGridColumn<ItemCategory>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "default_costing_method",
    header: "Default costing",
    render: (row) => row.default_costing_method.replace("_", " "),
    width: "180px",
  },
];

export function ItemCategoryListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.category.manage");
  const categories = useItemCategories();
  const rows = categories.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Item Categories</h1>
        {canManage && (
          <Link
            to="/inventory/item-categories/new"
            className="btn-ink"
          >
            New category
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/item-categories/$categoryId", params: { categoryId: row.id } })}
          loading={categories.isPending}
          emptyMessage="No item categories yet."
          hasMore={categories.hasNextPage}
          onLoadMore={() => void categories.fetchNextPage()}
          loadingMore={categories.isFetchingNextPage}
          label="Item categories"
        />
      </div>
    </div>
  );
}
