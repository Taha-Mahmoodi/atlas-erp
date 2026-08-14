/**
 * The maintenance module's own landing page (STRUCTURE §4: modules/maintenance/pages/).
 * PLAN 15.9 — equipment register, maintenance orders, preventive plans.
 */

import { Link } from "@tanstack/react-router";

const TILE =
  "rounded-card border border-line bg-surface p-4 shadow-card transition-colors duration-150 hover:border-primary";

export function MaintenanceHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Maintenance</h1>
      </header>
      <section className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        <Link to="/maintenance/equipment" className={TILE}>
          <span className="block text-sm font-medium text-ink">Equipment</span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            The register of maintainable equipment
          </span>
        </Link>
        <Link to="/maintenance/orders" className={TILE}>
          <span className="block text-sm font-medium text-ink">Maintenance Orders</span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            Corrective and preventive work with schedule/start/complete lifecycle
          </span>
        </Link>
        <Link to="/maintenance/plans" className={TILE}>
          <span className="block text-sm font-medium text-ink">Preventive Plans</span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            Interval-based plans that generate preventive orders when due
          </span>
        </Link>
      </section>
    </div>
  );
}
