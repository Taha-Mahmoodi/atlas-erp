/**
 * The role-based home page (PLAN 15.3, CLAUDE.md's "Fiori-inspired role-based home pages"):
 * a KPI row from the reporting dashboard (only the cards the caller's role can see) plus a
 * tile grid of the modules the caller has any access to, each linking into its section.
 */

import { useMe } from "@/lib/session";
import { DashboardKpis } from "@/modules/reporting/components/DashboardKpis";
import { useDashboard } from "@/modules/reporting/hooks";
import { modulesFor } from "@/shell/moduleRegistry";
import { ModuleLink } from "@/shell/ModuleLink";

export function HomePage() {
  const me = useMe();
  const dashboard = useDashboard();
  const permissions = me.data?.permissions ?? [];
  const modules = modulesFor(permissions);

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="text-xl font-semibold text-ink">
        {me.data?.full_name ? `Welcome, ${me.data.full_name}` : "Welcome"}
      </h1>

      <DashboardKpis data={dashboard.data} loading={dashboard.isPending} />

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
