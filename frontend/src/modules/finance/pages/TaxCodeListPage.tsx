/**
 * Tax codes settings list (STRUCTURE §4, PLAN 15.12). Shows ALL codes including inactive
 * ones (unlike the form pickers, which filter to active); row click opens the edit form.
 * Writes need finance.tax.manage; reads only finance.tax.read.
 */

import { Link, useNavigate } from "@tanstack/react-router";

import { getErrorMessage } from "@/lib/apiClient";
import { formatPercent } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useTaxCodesPage } from "@/modules/finance/hooks";
import type { TaxCode } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<TaxCode>[] = [
  { key: "code", header: "Code", render: (row) => row.code, width: "120px" },
  { key: "name", header: "Name", render: (row) => row.name },
  {
    key: "rate_percent",
    header: "Rate",
    render: (row) => <span className="tabular-nums">{formatPercent(row.rate_percent)}</span>,
    align: "right",
    width: "90px",
  },
  { key: "jurisdiction", header: "Jurisdiction", render: (row) => row.jurisdiction ?? "—", width: "130px" },
  { key: "is_inclusive", header: "Inclusive", render: (row) => (row.is_inclusive ? "Yes" : "No"), width: "90px" },
  {
    key: "is_active",
    header: "Status",
    render: (row) => (row.is_active ? "Active" : "Inactive"),
    width: "90px",
  },
];

export function TaxCodeListPage() {
  const navigate = useNavigate();
  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.tax.manage");
  const taxCodes = useTaxCodesPage();
  const rows = taxCodes.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Tax Codes</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Tax Codes</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/finance/tax-codes/new"
                className="btn-ink"
              >
                New tax code
              </Link>
            )}
          </div>
        </div>
      </header>

      <div>
        {taxCodes.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(taxCodes.error, "Unable to load tax codes.")}
          </p>
        ) : (
        <DataGrid
          columns={COLUMNS}
          rows={rows}
          rowKey={(row) => row.id}
          {...(canManage
            ? {
                onRowClick: (row: TaxCode) =>
                  void navigate({ to: "/finance/tax-codes/$taxCodeId", params: { taxCodeId: row.id } }),
              }
            : {})}
          loading={taxCodes.isPending}
          emptyMessage="No tax codes yet — the industry template usually seeds them at onboarding."
          hasMore={taxCodes.hasNextPage}
          onLoadMore={() => void taxCodes.fetchNextPage()}
          loadingMore={taxCodes.isFetchingNextPage}
          label="Tax codes"
        />
        )}
      </div>
    </div>
  );
}
