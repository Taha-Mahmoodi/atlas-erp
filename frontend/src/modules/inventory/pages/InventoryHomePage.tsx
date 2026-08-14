/**
 * The inventory module's own landing page (STRUCTURE §4: modules/inventory/pages/). Links
 * into this slice's areas; warehouses/bins/moves/on-hand/valuation and stock counts land as
 * those slices ship (PLAN 15.5).
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/inventory/items", label: "Items", description: "Item master data" },
  { to: "/inventory/item-categories", label: "Item Categories", description: "Costing method and GL account defaults" },
  { to: "/inventory/uoms", label: "Units of Measure", description: "Reference units and per-item conversions" },
  { to: "/inventory/warehouses", label: "Warehouses", description: "Warehouses and their bins" },
  { to: "/inventory/stock-moves", label: "Stock Moves", description: "Receipts, issues, transfers, adjustments" },
  { to: "/inventory/stock-on-hand", label: "Stock On-Hand", description: "Current quantities by item and bin" },
  { to: "/inventory/stock-valuation", label: "Stock Valuation", description: "Moving-average value and FIFO cost layers" },
  { to: "/inventory/stock-counts", label: "Stock Counts", description: "Physical and cycle counts, variance posting" },
] as const;

export function InventoryHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Inventory</h1>
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
