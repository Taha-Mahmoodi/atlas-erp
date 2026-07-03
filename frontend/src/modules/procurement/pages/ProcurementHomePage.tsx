/**
 * The procurement module's own landing page (STRUCTURE §4: modules/procurement/pages/). Links
 * into this slice's areas; requisitions, RFQs, POs, goods receipts, and invoice matches land
 * as those slices ship (PLAN 15.6).
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/procurement/vendors", label: "Vendors", description: "Vendor master data and approved items" },
  { to: "/procurement/approval-rules", label: "Approval Rules", description: "Value thresholds for requisition/PO approval" },
] as const;

export function ProcurementHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">Procurement</h1>
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
