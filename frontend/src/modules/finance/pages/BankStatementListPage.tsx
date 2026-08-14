/**
 * Bank statements list (STRUCTURE §4). Keyset-paginated (D-014); row click opens the
 * reconciliation workbench.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { formatDate, formatMoney } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { StatusPill } from "@/components/StatusPill";
import { useAccountLookup, useBankStatements } from "@/modules/finance/hooks";
import type { BankStatement } from "@/modules/finance/types";

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
    { key: "status", header: "Status", render: (row) => <StatusPill status={row.status} />, width: "160px" },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Bank Statements</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Bank Statements</h1>
          <div className="flex items-center gap-2.5">
            {canImport && (
              <Link
                to="/finance/bank-statements/import"
                className="btn-ink"
              >
                Import statement
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
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
