/**
 * Tenant roles list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the role's
 * detail page with its granted permission keys.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDateTime } from "@/lib/format";
import { getErrorMessage } from "@/lib/apiClient";
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
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/admin" className="hover:text-ink">
            Admin
          </Link>{" "}
          / <span className="text-ink">Roles</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Roles</h1>
          <div className="flex items-center gap-2.5">
            <Link
              to="/admin/roles/new"
              className="btn-ink"
            >
              New role
            </Link>
          </div>
        </div>
      </header>

      <div>
        {roles.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(roles.error, "Unable to load roles.")}
          </p>
        ) : (
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
        )}
      </div>
    </div>
  );
}
