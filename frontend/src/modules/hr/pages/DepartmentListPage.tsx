/**
 * Departments list (STRUCTURE §4). Keyset-paginated (D-014); row click opens edit. Parent and
 * cost-center render as code labels via the option lookups.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useCostCenterOptions, useDepartmentOptions, useDepartments } from "@/modules/hr/hooks";
import type { Department } from "@/modules/hr/types";

export function DepartmentListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("hr.department.manage");

  const departments = useDepartments();
  const departmentOptions = useDepartmentOptions();
  const costCenters = useCostCenterOptions();
  const rows = departments.data?.pages.flatMap((page) => page.items) ?? [];

  const departmentLabel = (id: string) => {
    const department = departmentOptions.data?.items.find((d) => d.id === id);
    return department ? `${department.code} — ${department.name}` : id;
  };
  const costCenterLabel = (id: string) => {
    const costCenter = costCenters.data?.items.find((c) => c.id === id);
    return costCenter ? `${costCenter.code} — ${costCenter.name}` : id;
  };

  const columns: DataGridColumn<Department>[] = [
    { key: "code", header: "Code", render: (row) => row.code, width: "110px" },
    { key: "name", header: "Name", render: (row) => row.name },
    { key: "parent_id", header: "Parent", render: (row) => (row.parent_id ? departmentLabel(row.parent_id) : "—") },
    {
      key: "cost_center_id",
      header: "Cost center",
      render: (row) => (row.cost_center_id ? costCenterLabel(row.cost_center_id) : "—"),
    },
    { key: "is_active", header: "Active", render: (row) => (row.is_active ? "Yes" : "No"), width: "80px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Departments</h1>
        {canManage && (
          <Link
            to="/hr/departments/new"
            className="btn-ink"
          >
            New department
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/departments/$departmentId", params: { departmentId: row.id } })}
          loading={departments.isPending}
          emptyMessage="No departments yet."
          hasMore={departments.hasNextPage}
          onLoadMore={() => void departments.fetchNextPage()}
          loadingMore={departments.isFetchingNextPage}
          label="Departments"
        />
      </div>
    </div>
  );
}
