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
import { StatusPill } from "@/components/StatusPill";

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
      <StatusPill status={row.is_active ? "ACTIVE" : "INACTIVE"} />
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
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/procurement" className="hover:underline">
            Procurement
          </Link>{" "}
          / <span className="text-ink">Approval Rules</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Approval Rules</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/procurement/approval-rules/new"
                className="btn-ink"
              >
                New rule
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
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
