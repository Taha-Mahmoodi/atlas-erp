/**
 * Projects list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click
 * opens the project workbench. Mirrors sales' CustomerListPage.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useFunctionalCurrency } from "@/modules/finance/hooks";
import { useProjects } from "@/modules/projects/hooks";
import type { Project, ProjectStatus } from "@/modules/projects/types";

export function ProjectListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("projects.project.manage");
  const [status, setStatus] = useState<ProjectStatus | "">("");

  const currency = useFunctionalCurrency();
  const projects = useProjects(status ? { status } : {});
  const rows = projects.data?.pages.flatMap((page) => page.items) ?? [];

  const columns: DataGridColumn<Project>[] = [
    { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
    { key: "name", header: "Name", render: (row) => row.name },
    { key: "start_date", header: "Start", render: (row) => row.start_date ?? "—", width: "110px" },
    { key: "end_date", header: "End", render: (row) => row.end_date ?? "—", width: "110px" },
    {
      key: "budget_amount",
      header: "Budget",
      align: "right",
      width: "140px",
      render: (row) =>
        row.budget_amount === null ? "—" : formatMoney(row.budget_amount, currency.data ?? "—"),
    },
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "120px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Projects</h1>
        {canManage && (
          <Link
            to="/projects/new"
            className="btn-ink"
          >
            New project
          </Link>
        )}
      </div>

      <div className="mt-4">
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as ProjectStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="PLANNING">Planning</option>
          <option value="ACTIVE">Active</option>
          <option value="CLOSED">Closed</option>
          <option value="CANCELLED">Cancelled</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/projects/$projectId", params: { projectId: row.id } })}
          loading={projects.isPending}
          emptyMessage={status ? "No projects match this filter." : "No projects yet."}
          hasMore={projects.hasNextPage}
          onLoadMore={() => void projects.fetchNextPage()}
          loadingMore={projects.isFetchingNextPage}
          label="Projects"
        />
      </div>
    </div>
  );
}
