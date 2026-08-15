/**
 * The role-based KPI card row (D-058): renders whichever KPIs the dashboard bundle contains —
 * the backend already omitted the ones the caller's role can't see, so presence IS permission.
 * Shared by the shell home page (headline row) and the reporting dashboard page. Cards with an
 * obvious source page drill through to it on click.
 */

import { useNavigate } from "@tanstack/react-router";

import { KpiCard } from "@/components/KpiCard";
import { formatMoney, formatPercent } from "@/lib/format";
import type { DashboardResponse } from "@/modules/reporting/types";

type DrillPath =
  | "/finance/cash-flow"
  | "/finance/ar-aging"
  | "/finance/ap-aging"
  | "/inventory/stock-valuation"
  | "/sales/orders"
  | "/procurement/purchase-orders"
  | "/sales/deliveries";

interface KpiTile {
  key: string;
  label: string;
  value: string;
  secondary?: string;
  /** Drill-through target — only set when the source page actually exists. */
  to?: DrillPath;
}

export function DashboardKpis({
  data,
  loading,
}: {
  data: DashboardResponse | undefined;
  loading: boolean;
}) {
  const navigate = useNavigate();

  const raw: (KpiTile | false | undefined)[] = data
    ? [
        data.cash_position && {
          key: "cash",
          label: "Cash position",
          value: formatMoney(data.cash_position.value, data.cash_position.currency),
          to: "/finance/cash-flow" as const,
        },
        data.ar_aging && {
          key: "ar",
          label: "AR outstanding",
          value: formatMoney(data.ar_aging.total, data.ar_aging.currency),
          to: "/finance/ar-aging" as const,
        },
        data.ap_aging && {
          key: "ap",
          label: "AP outstanding",
          value: formatMoney(data.ap_aging.total, data.ap_aging.currency),
          to: "/finance/ap-aging" as const,
        },
        data.inventory_value && {
          key: "inv",
          label: "Inventory value",
          value: formatMoney(data.inventory_value.value, data.inventory_value.currency),
          to: "/inventory/stock-valuation" as const,
        },
        data.open_sales_orders && {
          key: "oso",
          label: "Open sales orders",
          value: String(data.open_sales_orders.count),
          secondary: formatMoney(data.open_sales_orders.total, data.open_sales_orders.currency),
          to: "/sales/orders" as const,
        },
        data.open_purchase_orders && {
          key: "opo",
          label: "Open purchase orders",
          value: String(data.open_purchase_orders.count),
          secondary: formatMoney(
            data.open_purchase_orders.total,
            data.open_purchase_orders.currency,
          ),
          to: "/procurement/purchase-orders" as const,
        },
        data.otd_percent && {
          key: "otd",
          label: "On-time delivery",
          value: formatPercent(data.otd_percent.percent),
          secondary: `${data.otd_percent.on_time} / ${data.otd_percent.total} deliveries`,
          to: "/sales/deliveries" as const,
        },
        // WIP has no dedicated page yet (manufacturing UI, PLAN 15.8) — no drill-through.
        data.wip_value && {
          key: "wip",
          label: "WIP value",
          value: formatMoney(data.wip_value.value, data.wip_value.currency),
        },
        // D-075: the operational card. A failed background job is a posting that did not
        // happen, so it belongs on the row a person already opens rather than behind an
        // endpoint they would have to remember. Rendered even at zero — a card reading "0" is
        // the signal that the check ran. No drill-through: there is no jobs page yet, and the
        // drill-down lives at GET /api/v1/jobs?status=FAILED.
        data.failed_jobs && {
          key: "jobs",
          label: "Failed background jobs",
          value: String(data.failed_jobs.count),
          secondary: `last ${data.failed_jobs.window_days} days`,
        },
      ]
    : [];
  const tiles = raw.filter((tile): tile is KpiTile => Boolean(tile));

  if (!loading && tiles.length === 0) return null;

  // 240px minimum, not 200: the register's stat value is 26px, and a full money string
  // ("USD 237,400.00") overflows a 200px card at that size. Four across on a 1120px content
  // column, which is the register's own stat row.
  return (
    <section className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
      {loading
        ? Array.from({ length: 3 }, (_, index) => (
            <KpiCard key={index} label="Loading" value="" loading />
          ))
        : tiles.map((tile) => {
            const to = tile.to;
            return (
              <KpiCard
                key={tile.key}
                label={tile.label}
                value={tile.value}
                {...(tile.secondary !== undefined ? { secondary: tile.secondary } : {})}
                {...(to ? { onClick: () => void navigate({ to }) } : {})}
              />
            );
          })}
    </section>
  );
}
