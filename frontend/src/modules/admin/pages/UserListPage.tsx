/**
 * Tenant users list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the detail
 * page with role assignment.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDateTime } from "@/lib/format";
import { getErrorMessage } from "@/lib/apiClient";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useUsers } from "@/modules/admin/hooks";
import type { User } from "@/modules/admin/types";

const COLUMNS: DataGridColumn<User>[] = [
  { key: "email", header: "Email", render: (row) => row.email },
  { key: "full_name", header: "Name", render: (row) => row.full_name ?? "—" },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (row.is_active ? "Active" : "Inactive"),
    width: "100px",
  },
  { key: "created_at", header: "Created", render: (row) => formatDateTime(row.created_at), width: "180px" },
];

export function UserListPage() {
  const navigate = useNavigate();
  const users = useUsers();
  const rows = users.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Users</h1>
        <Link
          to="/admin/users/new"
          className="btn-ink"
        >
          New user
        </Link>
      </div>

      <div className="mt-4">
        {users.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(users.error, "Unable to load users.")}
          </p>
        ) : (
          <DataGrid
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.id}
            onRowClick={(row) => void navigate({ to: "/admin/users/$userId", params: { userId: row.id } })}
            loading={users.isPending}
            emptyMessage="No users yet."
            hasMore={users.hasNextPage}
            onLoadMore={() => void users.fetchNextPage()}
            loadingMore={users.isFetchingNextPage}
            label="Users"
          />
        )}
      </div>
    </div>
  );
}
