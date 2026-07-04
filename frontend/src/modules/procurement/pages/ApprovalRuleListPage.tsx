/**
 * Approval rules list (STRUCTURE §4). One value-threshold rule per (document_type,
 * currency_code) in practice — no rule for a document type/currency means that document type
 * never gates on approval (auto-approves silently), so an empty list here is a meaningful,
 * valid state, not an error.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useApprovalRules } from "@/modules/procurement/hooks";
import type { ApprovalRule } from "@/modules/procurement/types";

const COLUMNS: DataGridColumn<ApprovalRule>[] = [
  { key: "document_type", header: "Document type", render: (row) => row.document_type.replace("_", " "), width: "180px" },
  {
    key: "threshold_amount",
    header: "Threshold",
    align: "right",
    render: (row) => formatMoney(row.threshold_amount, row.currency_code),
    width: "150px",
  },
  { key: "description", header: "Description", render: (row) => row.description ?? "—" },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (
      <span
        className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${
          row.is_active ? "bg-success-tint text-success" : "bg-panel text-ink-muted"
        }`}
      >
        {row.is_active ? "Active" : "Inactive"}
      </span>
    ),
    width: "100px",
  },
];

export function ApprovalRuleListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("procurement.approval_rule.manage");
  const rules = useApprovalRules();
  const rows = rules.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Approval Rules</h1>
        {canManage && (
          <Link
            to="/procurement/approval-rules/new"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            New rule
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/procurement/approval-rules/$ruleId", params: { ruleId: row.id } })}
          loading={rules.isPending}
          emptyMessage="No approval rules yet — requisitions and POs auto-approve until one exists."
          hasMore={rules.hasNextPage}
          onLoadMore={() => void rules.fetchNextPage()}
          loadingMore={rules.isFetchingNextPage}
          label="Approval rules"
        />
      </div>
    </div>
  );
}
