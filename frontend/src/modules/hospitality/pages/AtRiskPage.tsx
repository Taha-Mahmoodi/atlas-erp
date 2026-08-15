/**
 * The at-risk list (STRUCTURE §4): dishes the storeroom covers only a few more portions of, worst
 * first, with the ingredient that runs out first.
 *
 * ADVISORY and read-only, and the page says so rather than implying otherwise. The number is
 * derived from on-hand alone (a kitchen cannot cook an open PO) and it OVER-reports on shared
 * ingredients, because every dish is costed against the whole storeroom. It exists to prompt a
 * human to 86 a dish — that stored row, not this scan, is what the guest-facing read path serves.
 */

import { Link } from "@tanstack/react-router";
import { useState } from "react";

import { DataGrid, type DataGridColumn } from "@/components/DataGrid";
import { useAtRisk, useMenu } from "@/modules/hospitality/hooks";
import type { MenuItemAtRisk } from "@/modules/hospitality/types";

const DEFAULT_THRESHOLD = 5;

export function AtRiskPage() {
  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD);
  const atRisk = useAtRisk({ threshold });
  const menu = useMenu();

  const itemLabel = (itemId: string) => {
    const item = menu.data?.items.find((entry) => entry.item_id === itemId);
    return item ? `${item.item_code} — ${item.name}` : itemId;
  };

  const columns: DataGridColumn<MenuItemAtRisk>[] = [
    { key: "item", header: "Dish", render: (row) => itemLabel(row.item_id) },
    {
      key: "max_producible",
      header: "Portions covered",
      align: "right",
      width: "150px",
      render: (row) => row.max_producible,
    },
    {
      key: "limiting_item",
      header: "Runs out first",
      render: (row) => itemLabel(row.limiting_item_id),
    },
  ];

  return (
    <div>
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/hospitality" className="hover:underline">
            Hospitality
          </Link>{" "}
          / <span className="text-ink">At risk</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">At risk</h1>
        <p className="mt-1 max-w-2xl text-[13px] text-ink-muted">
          Advisory. Counted from on-hand stock only, and generous on shared ingredients — a dish
          here is worth checking, not automatically 86'd.
        </p>
      </header>

      <div className="flex items-center gap-2">
        <label htmlFor="at-risk-threshold" className="text-xs font-medium text-ink-muted">
          Warn at or below
        </label>
        <input
          id="at-risk-threshold"
          type="number"
          min={0}
          value={threshold}
          onChange={(event) => setThreshold(Math.max(0, Number(event.target.value) || 0))}
          className="w-24 rounded-control border border-line bg-surface px-2 py-1.5 text-sm tabular-nums text-ink"
        />
        <span className="text-xs text-ink-muted">portions</span>
      </div>

      <div className="mt-4">
        <DataGrid
          columns={columns}
          rows={atRisk.data ?? []}
          rowKey={(row) => row.item_id}
          loading={atRisk.isPending}
          emptyMessage="No dish is down to its last few portions."
          isFiltered={threshold !== DEFAULT_THRESHOLD}
          onClearFilters={() => setThreshold(DEFAULT_THRESHOLD)}
          label="Dishes at risk"
        />
      </div>
    </div>
  );
}
