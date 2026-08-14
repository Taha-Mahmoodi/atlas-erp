/**
 * Exchange rates settings list (STRUCTURE §4, PLAN 15.12, D-019). Filterable by currency
 * pair and rate type; rates are append-only per (date, pair, type) — corrections are a new
 * row on the same date, so there is no edit page, only New.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDate } from "@/lib/format";
import { useMe } from "@/lib/session";
import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useCurrencyOptions, useExchangeRates } from "@/modules/finance/hooks";
import type { ExchangeRate, RateType } from "@/modules/finance/types";

const COLUMNS: DataGridColumn<ExchangeRate>[] = [
  { key: "rate_date", header: "Date", render: (row) => formatDate(row.rate_date), width: "130px" },
  {
    key: "pair",
    header: "Pair",
    render: (row) => `${row.from_currency_code} → ${row.to_currency_code}`,
    width: "140px",
  },
  { key: "rate_type", header: "Type", render: (row) => row.rate_type, width: "100px" },
  { key: "rate", header: "Rate", render: (row) => <span className="tabular-nums">{row.rate}</span>, align: "right" },
];

const FILTER_SELECT = "rounded-control border border-line bg-surface px-2 py-1.5 text-sm text-ink";

export function ExchangeRateListPage() {
  const [fromCode, setFromCode] = useState("");
  const [toCode, setToCode] = useState("");
  const [rateType, setRateType] = useState<RateType | "">("");

  const me = useMe();
  const canManage = (me.data?.permissions ?? []).includes("finance.fx.manage");
  const currencies = useCurrencyOptions();
  const rates = useExchangeRates({
    ...(fromCode ? { from_currency_code: fromCode } : {}),
    ...(toCode ? { to_currency_code: toCode } : {}),
    ...(rateType ? { rate_type: rateType } : {}),
  });
  const rows = rates.data?.pages.flatMap((page) => page.items) ?? [];
  const codes = (currencies.data?.items ?? []).map((currency) => currency.code);

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/finance">Finance</Link> / <span className="text-ink">Exchange Rates</span>
        </p>
        <div className="mt-1.5 flex items-start justify-between gap-4">
          <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Exchange Rates</h1>
          <div className="flex items-center gap-2.5">
            {canManage && (
              <Link
                to="/finance/exchange-rates/new"
                className="btn-ink"
              >
                New rate
              </Link>
            )}
          </div>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2">
        <select aria-label="From currency" value={fromCode} onChange={(event) => setFromCode(event.target.value)} className={FILTER_SELECT}>
          <option value="">From: all</option>
          {codes.map((code) => (
            <option key={code} value={code}>
              From: {code}
            </option>
          ))}
        </select>
        <select aria-label="To currency" value={toCode} onChange={(event) => setToCode(event.target.value)} className={FILTER_SELECT}>
          <option value="">To: all</option>
          {codes.map((code) => (
            <option key={code} value={code}>
              To: {code}
            </option>
          ))}
        </select>
        <select
          aria-label="Rate type"
          value={rateType}
          onChange={(event) => setRateType(event.target.value as RateType | "")}
          className={FILTER_SELECT}
        >
          <option value="">All types</option>
          <option value="SPOT">Spot</option>
          <option value="CLOSING">Closing</option>
        </select>
      </div>

      <div className="mt-4">
        {rates.isError ? (
          <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
            {getErrorMessage(rates.error, "Unable to load exchange rates.")}
          </p>
        ) : (
          <DataGrid
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.id}
            loading={rates.isPending}
            emptyMessage="No exchange rates yet."
            isFiltered={Boolean(fromCode || toCode || rateType)}
            onClearFilters={() => {
              setFromCode("");
              setToCode("");
              setRateType("");
            }}
            hasMore={rates.hasNextPage}
            onLoadMore={() => void rates.fetchNextPage()}
            loadingMore={rates.isFetchingNextPage}
            label="Exchange rates"
          />
        )}
      </div>
    </div>
  );
}
