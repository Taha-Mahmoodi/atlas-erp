/**
 * Equipment register list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014);
 * row click opens edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useEquipmentList } from "@/modules/maintenance/hooks";
import type { Equipment, EquipmentStatus } from "@/modules/maintenance/types";

const STATUS_TONE: Record<EquipmentStatus, string> = {
  ACTIVE: "bg-success-tint text-success",
  INACTIVE: "bg-panel text-ink-muted",
  RETIRED: "bg-danger-tint text-danger",
};

function StatusChip({ status }: { status: EquipmentStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

const COLUMNS: DataGridColumn<Equipment>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "location", header: "Location", render: (row) => row.location ?? "—", width: "160px" },
  { key: "manufacturer", header: "Manufacturer", render: (row) => row.manufacturer ?? "—", width: "160px" },
  { key: "serial_number", header: "Serial", render: (row) => row.serial_number ?? "—", width: "140px" },
  { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "110px" },
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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Equipment</h1>
        {canManage && (
          <Link
            to="/maintenance/equipment/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New equipment
          </Link>
        )}
      </div>

      <div className="mt-4">
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
          hasMore={equipment.hasNextPage}
          onLoadMore={() => void equipment.fetchNextPage()}
          loadingMore={equipment.isFetchingNextPage}
          label="Equipment"
        />
      </div>
    </div>
  );
}
