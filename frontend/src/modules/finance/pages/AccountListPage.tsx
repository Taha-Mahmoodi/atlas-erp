/**
 * Chart of accounts (STRUCTURE §4: modules/finance/pages/AccountListPage.tsx). Filterable,
 * keyset-paginated (D-014); row click opens the account for edit.
 */

import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useMe } from "@/lib/session";
import { useAccounts } from "@/modules/finance/hooks";
import { ACCOUNT_TYPES, type Account, type AccountType } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<Account>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "100px" },
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "account_type", header: "Type", render: (row) => row.account_type },
  {
    key: "is_postable",
    header: "Postable",
    align: "center",
    render: (row) => (row.is_postable ? "Yes" : "No"),
  },
  {
    key: "is_active",
    header: "Active",
    align: "center",
    render: (row) => (row.is_active ? "Yes" : "No"),
  },
];

export function AccountListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.account.manage");
  const [accountType, setAccountType] = useState<AccountType | "">("");
  const [activeOnly, setActiveOnly] = useState(false);

  const filters = {
    ...(accountType ? { account_type: accountType } : {}),
    ...(activeOnly ? { is_active: true } : {}),
  };
  const accounts = useAccounts(filters);
  const rows = accounts.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Chart of Accounts</h1>
        {canManage && (
          <Link
            to="/finance/accounts/new"
            className="btn-ink"
          >
            New account
          </Link>
        )}
      </div>

      <div className="mt-4 flex items-center gap-4">
        <select
          value={accountType}
          onChange={(event) => setAccountType(event.target.value as AccountType | "")}
          className="rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink"
        >
          <option value="">All types</option>
          {ACCOUNT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-ink-muted">
          <input
            type="checkbox"
            checked={activeOnly}
            onChange={(event) => setActiveOnly(event.target.checked)}
            className="size-4 accent-primary"
          />
          Active only
        </label>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          onRowClick={(row) => void navigate({ to: "/finance/accounts/$accountId", params: { accountId: row.id } })}
          loading={accounts.isPending}
          emptyMessage="No accounts yet — create the first one to start the chart of accounts."
          hasMore={accounts.hasNextPage}
          onLoadMore={() => void accounts.fetchNextPage()}
          loadingMore={accounts.isFetchingNextPage}
          label="Chart of accounts"
        />
      </div>
    </div>
  );
}
