/**
 * Units of measure list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useUoms } from "@/modules/inventory/hooks";
import type { Uom } from "@/modules/inventory/types";

const COLUMNS: DataGridColumn<Uom>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
];

export function UomListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("inventory.uom.manage");
  const uoms = useUoms();
  const rows = uoms.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Units of Measure</h1>
        {canManage && (
          <Link
            to="/inventory/uoms/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New UoM
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/inventory/uoms/$uomId", params: { uomId: row.id } })}
          loading={uoms.isPending}
          emptyMessage="No units of measure yet."
          hasMore={uoms.hasNextPage}
          onLoadMore={() => void uoms.fetchNextPage()}
          loadingMore={uoms.isFetchingNextPage}
          label="Units of measure"
        />
      </div>
    </div>
  );
}
