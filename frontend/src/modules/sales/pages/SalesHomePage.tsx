/**
 * The sales module's own landing page (STRUCTURE §4: modules/sales/pages/). Slices 1-2/4 of
 * PLAN 15.7 — customers, pricing, quotes, and orders; deliveries/billing/returns land in later
 * slices.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/sales/customers", label: "Customers", description: "Customer master data and credit terms" },
  { to: "/sales/customer-groups", label: "Customer Groups", description: "Grouping used by price lists" },
  { to: "/sales/price-lists", label: "Price Lists", description: "Condition-style pricing per currency/group/date" },
  { to: "/sales/price-quote", label: "Price Quote", description: "Look up what a customer would pay for an item" },
  { to: "/sales/quotes", label: "Quotes", description: "Customer quotes and their conversion to orders" },
  { to: "/sales/orders", label: "Sales Orders", description: "Confirmed commitments, ATP and credit checks" },
] as const;

export function SalesHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">Sales</h1>
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
