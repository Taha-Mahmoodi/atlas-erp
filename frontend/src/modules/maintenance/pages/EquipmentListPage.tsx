/**
 * Equipment register list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014);
 * row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useEquipmentList } from "@/modules/maintenance/hooks";
import type { Equipment, EquipmentStatus } from "@/modules/maintenance/types";

const COLUMNS: DataGridColumn<Equipment>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "location", header: "Location", render: (row) => row.location ?? "—", width: "160px" },
  { key: "manufacturer", header: "Manufacturer", render: (row) => row.manufacturer ?? "—", width: "160px" },
  { key: "serial_number", header: "Serial", render: (row) => row.serial_number ?? "—", width: "140px" },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "110px" },
];

export function EquipmentListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("maintenance.equipment.manage");
  const [status, setStatus] = useState<EquipmentStatus | "">("");

  const equipment = useEquipmentList(status ? { status } : {});
  const rows = equipment.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/maintenance">Maintenance</Link> / <span className="text-ink">Equipment</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Equipment</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/maintenance/equipment/new"
                className="btn-ink"
              >
                New equipment
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as EquipmentStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="INACTIVE">Inactive</option>
          <option value="RETIRED">Retired</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/maintenance/equipment/$equipmentId", params: { equipmentId: row.id } })}
          loading={equipment.isPending}
          emptyMessage="No equipment yet."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={equipment.hasNextPage}
          onLoadMore={() => void equipment.fetchNextPage()}
          loadingMore={equipment.isFetchingNextPage}
          label="Equipment"
        />
      </div>
    </div>
  );
}
