/**
 * Bank statements list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the
 * reconciliation workbench.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useAccountLookup, useBankStatements } from "@/modules/finance/hooks";
import type { BankStatement, StatementStatus } from "@/modules/finance/types";

const STATUS_TONE: Record<StatementStatus, string> = {
  IMPORTED: "bg-warn-tint text-warn",
  PARTIALLY_RECONCILED: "bg-warn-tint text-warn",
  RECONCILED: "bg-success-tint text-success",
};

function StatusChip({ status }: { status: StatementStatus }) {
  return (
    <span className={`rounded-[4px] px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.02em] ${STATUS_TONE[status]}`}>
      {status.replace("_", " ")}
    </span>
  );
}

export function BankStatementListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canImport = (me.data?.permissions ?? []).includes("finance.bank.import");
  const accounts = useAccountLookup();
  const statements = useBankStatements();
  const rows = statements.data?.pages.flatMap((page) => page.items) ?? [];

  const accountLabel = (accountId: string) => {
    const account = accounts.data?.items.find((a) => a.id === accountId);
    return account ? `${account.code} — ${account.name}` : accountId;
  };

  const columns: DataGridColumn<BankStatement>[] = [
    { key: "bank_account_id", header: "Bank account", render: (row) => accountLabel(row.bank_account_id) },
    { key: "statement_date", header: "Statement date", render: (row) => formatDate(row.statement_date), width: "140px" },
    {
      key: "closing_balance",
      header: "Closing balance",
      align: "right",
      render: (row) => formatMoney(row.closing_balance, row.currency_code),
      width: "150px",
    },
    { key: "line_count", header: "Lines", align: "right", render: (row) => String(row.line_count), width: "80px" },
    { key: "status", header: "Status", render: (row) => <StatusChip status={row.status} />, width: "160px" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-ink">Bank Statements</h1>
        {canImport && (
          <Link
            to="/finance/bank-statements/import"
            className="rounded-control bg-primary px-3 py-1.5 text-sm font-medium text-surface transition-colors duration-150 hover:bg-primary-strong"
          >
            Import statement
          </Link>
        )}
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/bank-statements/$statementId", params: { statementId: row.id } })}
          loading={statements.isPending}
          emptyMessage="No bank statements yet."
          hasMore={statements.hasNextPage}
          onLoadMore={() => void statements.fetchNextPage()}
          loadingMore={statements.isFetchingNextPage}
          label="Bank statements"
        />
      </div>
    </div>
  );
}
