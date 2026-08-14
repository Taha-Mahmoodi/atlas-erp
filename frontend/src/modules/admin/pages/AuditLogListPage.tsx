/**
 * Audit-log viewer (STRUCTURE §4, D-010): the tenant's append-only change trail, newest
 * first, keyset-paginated. Filters (entity table/id, actor, action, date range) apply on
 * submit — not per keystroke — so typing an entity id doesn't fire a query per character.
 * Clicking a row opens its before/after diff below the grid (there is no per-row GET; the
 * list rows already carry the full diff).
 */

import { useState } from "react";

import { formatDateTime } from "@/lib/format";
import { getErrorMessage } from "@/lib/apiClient";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { AuditDiffView } from "@/modules/admin/components/AuditDiffView";
import type { AuditLogFilters } from "@/modules/admin/api";
import { useAuditLogs } from "@/modules/admin/hooks";
import type { AuditLog } from "@/modules/admin/types";
import { StatusPill } from "@/components/StatusPill";

const COLUMNS: DataGridColumn<AuditLog>[] = [
  { key: "created_at", header: "When", render: (row) => formatDateTime(row.created_at), width: "180px" },
  { key: "entity_table", header: "Entity", render: (row) => row.entity_table, width: "200px" },
  {
    key: "entity_id",
    header: "Entity ID",
    render: (row) => <span className="tabular-nums text-xs">{row.entity_id}</span>,
  },
  { key: "action", header: "Action", render: (row) => <StatusPill status={row.action} />, width: "100px" },
  {
    key: "actor_user_id",
    header: "Actor",
    render: (row) => (row.actor_user_id ? <span className="tabular-nums text-xs">{row.actor_user_id}</span> : "system"),
  },
];

const FILTER_INPUT =
  "rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink placeholder:text-ink-muted hover:border-ink-faint";

export function AuditLogListPage() {
  const [draft, setDraft] = useState({
    entity_table: "",
    entity_id: "",
    actor_user_id: "",
    action: "",
    created_from: "",
    created_to: "",
  });
  const [filters, setFilters] = useState<Omit<AuditLogFilters, "cursor">>({});
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const logs = useAuditLogs(filters);
  const rows = logs.data?.pages.flatMap((page) => page.items) ?? [];

  const apply = () => {
    setSelected(null);
    setFilters({
      ...(draft.entity_table.trim() ? { entity_table: draft.entity_table.trim() } : {}),
      ...(draft.entity_id.trim() ? { entity_id: draft.entity_id.trim() } : {}),
      ...(draft.actor_user_id.trim() ? { actor_user_id: draft.actor_user_id.trim() } : {}),
      ...(draft.action ? { action: draft.action } : {}),
      ...(draft.created_from ? { created_from: draft.created_from } : {}),
      ...(draft.created_to ? { created_to: draft.created_to } : {}),
    });
  };

  const set = (name: keyof typeof draft) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setDraft((prev) => ({ ...prev, [name]: event.target.value }));

  return (
    <div>
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Audit Log</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Append-only change trail for this tenant — every insert, update, and delete with its before/after diff.
      </p>

      <form
        className="mt-4 flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          apply();
        }}
      >
        <input
          aria-label="Entity table"
          placeholder="Entity table (e.g. journal_entries)"
          value={draft.entity_table}
          onChange={set("entity_table")}
          className={`${FILTER_INPUT} w-56`}
        />
        <input
          aria-label="Entity ID"
          placeholder="Entity ID"
          value={draft.entity_id}
          onChange={set("entity_id")}
          className={`${FILTER_INPUT} w-56`}
        />
        <input
          aria-label="Actor user ID"
          placeholder="Actor user ID"
          value={draft.actor_user_id}
          onChange={set("actor_user_id")}
          className={`${FILTER_INPUT} w-56`}
        />
        <select aria-label="Action" value={draft.action} onChange={set("action")} className={FILTER_INPUT}>
          <option value="">All actions</option>
          <option value="INSERT">Insert</option>
          <option value="UPDATE">Update</option>
          <option value="DELETE">Delete</option>
        </select>
        <label className="text-xs text-ink-muted">
          From
          <input type="date" aria-label="Created from" value={draft.created_from} onChange={set("created_from")} className={`${FILTER_INPUT} ml-1`} />
        </label>
        <label className="text-xs text-ink-muted">
          To
          <input type="date" aria-label="Created to" value={draft.created_to} onChange={set("created_to")} className={`${FILTER_INPUT} ml-1`} />
        </label>
        <button
          type="submit"
          className="btn-ink"
        >
          Apply
        </button>
      </form>

      <div className="mt-4">
        {logs.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(logs.error, "Unable to load the audit log.")}
          </p>
        ) : (
          <DataGrid
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.id}
            onRowClick={(row) => setSelected((prev) => (prev?.id === row.id ? null : row))}
            loading={logs.isPending}
            emptyMessage="No audit entries match these filters."
            hasMore={logs.hasNextPage}
            onLoadMore={() => void logs.fetchNextPage()}
            loadingMore={logs.isFetchingNextPage}
            density="compact"
            label="Audit log"
          />
        )}
      </div>

      {selected && (
        <section className="mt-4 rounded-card border border-line bg-surface p-4 shadow-card">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink">
              {selected.entity_table} <span className="font-normal text-ink-muted">· {selected.action}</span>
            </h2>
            <button type="button" onClick={() => setSelected(null)} className="text-xs font-medium text-ink-muted hover:text-ink">
              Close
            </button>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-4">
            <dt className="text-ink-muted">Entity ID</dt>
            <dd className="tabular-nums text-ink">{selected.entity_id}</dd>
            <dt className="text-ink-muted">Actor</dt>
            <dd className="tabular-nums text-ink">{selected.actor_user_id ?? "system"}</dd>
            <dt className="text-ink-muted">Request ID</dt>
            <dd className="tabular-nums text-ink">{selected.request_id ?? "—"}</dd>
            <dt className="text-ink-muted">IP</dt>
            <dd className="tabular-nums text-ink">{selected.request_ip ?? "—"}</dd>
          </dl>
          <div className="mt-3">
            <AuditDiffView diff={selected.diff} />
          </div>
        </section>
      )}
    </div>
  );
}
