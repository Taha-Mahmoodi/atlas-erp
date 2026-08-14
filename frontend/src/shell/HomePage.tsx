/**
 * The role-based home page (PLAN 15.3, CLAUDE.md's "Fiori-inspired role-based home pages"):
 * a KPI row from the reporting dashboard (only the cards the caller's role can see) plus a
 * tile grid of the modules the caller has any access to, each linking into its section.
 */

import { Icon } from "@/components/Icon";
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

  const today = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-6">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">
          {me.data?.full_name ? `Welcome back, ${me.data.full_name}` : "Welcome back"}
        </h1>
        <p className="mt-1 text-[13px] text-ink-muted">{today}</p>
      </header>

      <DashboardKpis data={dashboard.data} loading={dashboard.isPending} />

      <h2 className="mono-caps mt-9 mb-3 text-ink-muted">Modules</h2>
      {modules.length === 0 ? (
        <p className="text-[13px] text-ink-muted">
          Your role has no module access yet — ask an administrator to assign permissions.
        </p>
      ) : (
        <section className="grid grid-cols-[repeat(auto-fit,minmax(230px,1fr))] gap-4">
          {modules.map((entry) => (
            <ModuleLink
              key={entry.key}
              entry={entry}
              className="flex items-start gap-3 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card transition-colors duration-150 hover:border-primary"
            >
              <span
                aria-hidden="true"
                className="flex size-9 shrink-0 items-center justify-center rounded-[9px] bg-primary-tint text-primary"
              >
                <Icon name={entry.icon} size={17} />
              </span>
              <span className="min-w-0">
                <span className="block text-[13.5px] font-semibold text-ink">{entry.label}</span>
                <span className="mt-0.5 block text-[12px] leading-4 text-ink-muted">
                  {entry.description}
                </span>
              </span>
            </ModuleLink>
          ))}
        </section>
      )}
    </div>
  );
}
