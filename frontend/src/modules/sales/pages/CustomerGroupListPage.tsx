/**
 * Customer groups list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 * A group is what a price list can target instead of pricing every customer individually.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useCustomerGroups } from "@/modules/sales/hooks";
import type { CustomerGroup } from "@/modules/sales/types";

const COLUMNS: DataGridColumn<CustomerGroup>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
];

export function CustomerGroupListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("sales.customer.manage");
  const groups = useCustomerGroups();
  const rows = groups.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Customer Groups</h1>
        {canManage && (
          <Link
            to="/sales/customer-groups/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New group
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/sales/customer-groups/$customerGroupId", params: { customerGroupId: row.id } })}
          loading={groups.isPending}
          emptyMessage="No customer groups yet."
          hasMore={groups.hasNextPage}
          onLoadMore={() => void groups.fetchNextPage()}
          loadingMore={groups.isFetchingNextPage}
          label="Customer groups"
        />
      </div>
    </div>
  );
}
