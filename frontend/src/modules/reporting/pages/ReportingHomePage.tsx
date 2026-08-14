/**
 * The reporting module's own landing page (STRUCTURE §4: modules/reporting/pages/).
 * PLAN 15.12 — the KPI dashboard and the ad-hoc report builder.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/reporting/dashboard", label: "Dashboard", description: "Role-based KPI cards: cash, aging, inventory, orders, OTD, WIP" },
  { to: "/reporting/report-builder", label: "Report Builder", description: "Ad-hoc reports: pick an entity, columns, filters, group-by; export CSV" },
] as const;

export function ReportingHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Reporting</h1>
      </header>
      <section className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {SECTIONS.map((section) => (
          <Link
            key={section.to}
            to={section.to}
            className="rounded-card border border-line bg-surface p-4 shadow-card transition-colors duration-150 hover:border-primary"
          >
            <span className="block text-sm font-medium text-ink">{section.label}</span>
            <span className="mt-0.5 block text-xs text-ink-muted">{section.description}</span>
          </Link>
        ))}
      </section>
    </div>
  );
}
