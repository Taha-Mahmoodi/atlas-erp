/**
 * Positions list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useDepartmentOptions, usePositions } from "@/modules/hr/hooks";
import type { Position } from "@/modules/hr/types";

export function PositionListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hr.position.manage");

  const positions = usePositions();
  const departments = useDepartmentOptions();
  const rows = positions.data?.pages.flatMap((page) => page.items) ?? [];

  const departmentLabel = (id: string) => {
    const department = departments.data?.items.find((d) => d.id === id);
    return department ? `${department.code} — ${department.name}` : id;
  };

  const columns: DataGridColumn<Position>[] = [
    { key: "code", header: "Code", render: (row) => row.code, width: "110px" },
    { key: "title", header: "Title", render: (row) => row.title },
    {
      key: "department_id",
      header: "Department",
      render: (row) => (row.department_id ? departmentLabel(row.department_id) : "—"),
    },
    { key: "is_active", header: "Active", render: (row) => (row.is_active ? "Yes" : "No"), width: "80px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Positions</h1>
        {canManage && (
          <Link
            to="/hr/positions/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New position
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/positions/$positionId", params: { positionId: row.id } })}
          loading={positions.isPending}
          emptyMessage="No positions yet."
          hasMore={positions.hasNextPage}
          onLoadMore={() => void positions.fetchNextPage()}
          loadingMore={positions.isFetchingNextPage}
          label="Positions"
        />
      </div>
    </div>
  );
}
