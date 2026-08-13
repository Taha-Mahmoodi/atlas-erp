/**
 * Tenant roles list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the role's
 * detail page with its granted permission keys.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDateTime } from "@/lib/format";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useRoles } from "@/modules/admin/hooks";
import type { Role } from "@/modules/admin/types";

const COLUMNS: DataGridColumn<Role>[] = [
  { key: "name", header: "Name", render: (row) => row.name, width: "220px" },
  { key: "description", header: "Description", render: (row) => row.description ?? "—" },
  {
    key: "is_system",
    header: "Kind",
    render: (row) => (row.is_system ? "System" : "Custom"),
    width: "100px",
  },
  { key: "created_at", header: "Created", render: (row) => formatDateTime(row.created_at), width: "180px" },
];

export function RoleListPage() {
  const navigate = useNavigate();
  const roles = useRoles();
  const rows = roles.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Roles</h1>
        <Link
          to="/admin/roles/new"
          className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
        >
          New role
        </Link>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/admin/roles/$roleId", params: { roleId: row.id } })}
          loading={roles.isPending}
          emptyMessage="No roles yet."
          hasMore={roles.hasNextPage}
          onLoadMore={() => void roles.fetchNextPage()}
          loadingMore={roles.isFetchingNextPage}
          label="Roles"
        />
      </div>
    </div>
  );
}
