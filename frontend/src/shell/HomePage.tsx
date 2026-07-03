/**
 * The role-based home page (PLAN 15.3, CLAUDE.md's "Fiori-inspired role-based home pages"):
 * a KPI row from the reporting dashboard (only the cards the caller's role can see) plus a
 * tile grid of the modules the caller has any access to, each linking into its section.
 */

import { formatMoney, formatPercent } from "@/lib/format";
import { useMe } from "@/lib/session";
import { KpiCard } from "@/components/KpiCard";
import { useDashboard } from "@/modules/reporting/hooks";
import { modulesFor } from "@/shell/moduleRegistry";
import { ModuleLink } from "@/shell/ModuleLink";

export function HomePage() {
  const me = useMe();
  const dashboard = useDashboard();
  const permissions = me.data?.permissions ?? [];
  const modules = modulesFor(permissions);
  const d = dashboard.data;

  const kpis = d
    ? [
        d.cash_position && { key: "cash", label: "Cash position", value: formatMoney(d.cash_position.value, d.cash_position.currency) },
        d.ar_aging && { key: "ar", label: "AR outstanding", value: formatMoney(d.ar_aging.total, d.ar_aging.currency) },
        d.ap_aging && { key: "ap", label: "AP outstanding", value: formatMoney(d.ap_aging.total, d.ap_aging.currency) },
        d.inventory_value && { key: "inv", label: "Inventory value", value: formatMoney(d.inventory_value.value, d.inventory_value.currency) },
        d.open_sales_orders && {
          key: "oso",
          label: "Open sales orders",
          value: String(d.open_sales_orders.count),
          secondary: formatMoney(d.open_sales_orders.total, d.open_sales_orders.currency),
        },
        d.open_purchase_orders && {
          key: "opo",
          label: "Open purchase orders",
          value: String(d.open_purchase_orders.count),
          secondary: formatMoney(d.open_purchase_orders.total, d.open_purchase_orders.currency),
        },
        d.otd_percent && {
          key: "otd",
          label: "On-time delivery",
          value: formatPercent(d.otd_percent.percent),
          secondary: `${d.otd_percent.on_time} / ${d.otd_percent.total} deliveries`,
        },
        d.wip_value && { key: "wip", label: "WIP value", value: formatMoney(d.wip_value.value, d.wip_value.currency) },
      ].filter((kpi): kpi is Exclude<typeof kpi, false | undefined> => Boolean(kpi))
    : [];

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold text-ink">
        {me.data?.full_name ? `Welcome, ${me.data.full_name}` : "Welcome"}
      </h1>

      {(dashboard.isPending || kpis.length > 0) && (
        <section className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
          {dashboard.isPending
            ? Array.from({ length: 3 }, (_, index) => (
                <KpiCard key={index} label="Loading" value="" loading />
              ))
            : kpis.map((kpi) => (
                <KpiCard
                  key={kpi.key}
                  label={kpi.label}
                  value={kpi.value}
                  {...(kpi.secondary !== undefined ? { secondary: kpi.secondary } : {})}
                />
              ))}
        </section>
      )}

      <h2 className="mt-8 text-xs font-semibold uppercase tracking-[0.02em] text-ink-muted">
        Modules
      </h2>
      {modules.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">
          Your role has no module access yet — ask an administrator to assign permissions.
        </p>
      ) : (
        <section className="mt-3 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
          {modules.map((entry) => (
            <ModuleLink
              key={entry.key}
              entry={entry}
              className="flex items-start gap-3 rounded-card border border-line bg-surface p-4 shadow-card transition-colors duration-150 hover:border-primary"
            >
              <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-[6px] bg-primary-tint text-xs font-semibold text-primary"
              >
                {entry.label.slice(0, 2).toUpperCase()}
              </span>
              <span>
                <span className="block text-sm font-medium text-ink">{entry.label}</span>
                <span className="mt-0.5 block text-xs text-ink-muted">{entry.description}</span>
              </span>
            </ModuleLink>
          ))}
        </section>
      )}
    </div>
  );
}
