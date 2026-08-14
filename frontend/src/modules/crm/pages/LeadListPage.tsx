/**
 * Leads list (STRUCTURE §4). Filterable by status, keyset-paginated (D-014); row click opens
 * the lead workbench. Mirrors sales' CustomerListPage.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useLeads } from "@/modules/crm/hooks";
import type { Lead, LeadStatus } from "@/modules/crm/types";

const COLUMNS: DataGridColumn<Lead>[] = [
  { key: "lead_number", header: "Lead", render: (row) => row.lead_number, width: "140px" },
  { key: "company_name", header: "Company", render: (row) => row.company_name },
  { key: "contact_name", header: "Contact", render: (row) => row.contact_name ?? "—" },
  { key: "source", header: "Source", render: (row) => row.source ?? "—", width: "120px" },
  {
    key: "estimated_value",
    header: "Est. value",
    align: "right",
    width: "140px",
    render: (row) =>
      row.estimated_value !== null && row.currency_code
        ? formatMoney(row.estimated_value, row.currency_code)
        : "—",
  },
  { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "130px" },
];

export function LeadListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("crm.lead.manage");
  const [status, setStatus] = useState<LeadStatus | "">("");

  const leads = useLeads(status ? { status } : {});
  const rows = leads.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/crm" className="hover:underline">
            CRM
          </Link>{" "}
          / <span className="text-ink">Leads</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Leads</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/crm/leads/new"
                className="btn-ink"
              >
                New lead
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value as LeadStatus | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All statuses</option>
          <option value="NEW">New</option>
          <option value="CONTACTED">Contacted</option>
          <option value="QUALIFIED">Qualified</option>
          <option value="DISQUALIFIED">Disqualified</option>
          <option value="CONVERTED">Converted</option>
        </select>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/crm/leads/$leadId", params: { leadId: row.id } })}
          loading={leads.isPending}
          emptyMessage="No leads yet — capture the first one."
          isFiltered={Boolean(status)}
          onClearFilters={() => setStatus("")}
          hasMore={leads.hasNextPage}
          onLoadMore={() => void leads.fetchNextPage()}
          loadingMore={leads.isFetchingNextPage}
          label="Leads"
        />
      </div>
    </div>
  );
}
