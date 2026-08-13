/**
 * Employees list (STRUCTURE §4). Filterable by status/department, keyset-paginated (D-014).
 * The salary column renders the D-009 masking gracefully: the backend serializes compensation
 * to null for callers without `hr.employee.read_compensation`, shown here as "•••" rather than
 * pretending the value is absent. Creating requires BOTH manage and read_compensation (the
 * create payload carries initial pay), so the New button is gated on both.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useDepartmentOptions, useEmployees } from "@/modules/hr/hooks";
import type { Employee, EmploymentStatus } from "@/modules/hr/types";

const STATUS_TONE: Record<EmploymentStatus, string> = {
  ACTIVE: "bg-success-tint text-success",
  ON_LEAVE: "bg-warn-tint text-warn",
  TERMINATED: "bg-panel text-ink-muted",
};

function StatusChip({ status }: { status: EmploymentStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function EmployeeListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const canCreate =
    permissions.includes("hr.employee.manage") && permissions.includes("hr.employee.read_compensation");
  const canReadCompensation = permissions.includes("hr.employee.read_compensation");

  const [status, setStatus] = useState<EmploymentStatus | "">("");
  const [departmentId, setDepartmentId] = useState("");

  const employees = useEmployees({
    ...(status ? { status } : {}),
    ...(departmentId ? { department_id: departmentId } : {}),
  });
  const departments = useDepartmentOptions();
  const rows = employees.data?.pages.flatMap((page) => page.items) ?? [];

  const departmentLabel = (id: string) => {
    const department = departments.data?.items.find((d) => d.id === id);
    return department ? department.name : id;
  };

  const columns: DataGridColumn<Employee>[] = [
    { key: "employee_code", header: "Code", render: (row) => row.employee_code, width: "100px" },
    { key: "name", header: "Name", render: (row) => `${row.first_name} ${row.last_name}` },
    {
      key: "department_id",
      header: "Department",
      render: (row) => (row.department_id ? departmentLabel(row.department_id) : "—"),
    },
    { key: "hire_date", header: "Hired", render: (row) => row.hire_date, width: "110px" },
    {
      key: "base_salary",
      header: "Base salary",
      align: "right",
      // D-009: null + no read_compensation permission = masked, not merely unset.
      render: (row) =>
        row.base_salary !== null
          ? formatMoney(row.base_salary, row.currency_code ?? "")
          : canReadCompensation
            ? "—"
            : "•••",
      width: "130px",
    },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "120px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Employees</h1>
        {canCreate && (
          <Link
            to="/hr/employees/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New employee
          </Link>
        )}
      </div>

      <div className="mt-4 flex gap-2">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as EmploymentStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="ON_LEAVE">On leave</option>
          <option value="TERMINATED">Terminated</option>
        </select>
        <select
          value={departmentId}
          onChange={(event) => setDepartmentId(event.target.value)}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All departments</option>
          {(departments.data?.items ?? []).map((department) => (
            <option key={department.id} value={department.id}>
              {department.name}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/hr/employees/$employeeId", params: { employeeId: row.id } })}
          loading={employees.isPending}
          emptyMessage="No employees yet."
          hasMore={employees.hasNextPage}
          onLoadMore={() => void employees.fetchNextPage()}
          loadingMore={employees.isFetchingNextPage}
          label="Employees"
        />
      </div>
    </div>
  );
}
