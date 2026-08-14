/**
 * The procurement module's own landing page (STRUCTURE §4: modules/procurement/pages/). Final
 * slice of PLAN 15.6 — every area now has real UI.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/procurement/vendors", label: "Vendors", description: "Vendor master data and approved items" },
  { to: "/procurement/requisitions", label: "Requisitions", description: "Internal requests to buy" },
  { to: "/procurement/rfqs", label: "RFQs", description: "Request for quotation and vendor responses" },
  { to: "/procurement/purchase-orders", label: "Purchase Orders", description: "Firm commitments to a vendor" },
  { to: "/procurement/goods-receipts", label: "Goods Receipts", description: "Receiving against purchase orders" },
  { to: "/procurement/invoice-matches", label: "Invoice Matches", description: "3-way match against receipts and POs" },
  { to: "/procurement/approval-rules", label: "Approval Rules", description: "Value thresholds for requisition/PO approval" },
  { to: "/procurement/match-tolerances", label: "Match Tolerance", description: "Price/quantity variance thresholds" },
] as const;

export function ProcurementHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Procurement</h1>
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
