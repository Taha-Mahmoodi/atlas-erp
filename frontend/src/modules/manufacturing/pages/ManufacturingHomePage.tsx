/**
 * The manufacturing module's own landing page (STRUCTURE §4: modules/manufacturing/pages/).
 * Final slice of PLAN 15.8 — every area now has real UI.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/manufacturing/work-centers", label: "Work Centers", description: "Capacity and efficiency master data" },
  { to: "/manufacturing/boms", label: "Bills of Materials", description: "Versioned component structures per item" },
  { to: "/manufacturing/routings", label: "Routings", description: "Operation sequences with setup/run times" },
  { to: "/manufacturing/production-orders", label: "Production Orders", description: "Release, issue to WIP, finish to stock" },
  { to: "/manufacturing/mrp/runs", label: "MRP", description: "Planning runs, planned orders, capacity check" },
] as const;

export function ManufacturingHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Manufacturing</h1>
      <section className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
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
