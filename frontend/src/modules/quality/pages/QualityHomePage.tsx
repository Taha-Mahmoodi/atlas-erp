/**
 * The quality module's own landing page (STRUCTURE §4: modules/quality/pages/). PLAN 15.9 —
 * v1 QM is inspection lots only, so one tile.
 */

import { Link } from "@tanstack/react-router";

export function QualityHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Quality</h1>
      <section className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        <Link
          to="/quality/inspection-lots"
          className="rounded-card border border-line bg-surface p-4 shadow-card transition-colors duration-150 hover:border-primary"
        >
          <span className="block text-sm font-medium text-ink">Inspection Lots</span>
          <span className="mt-0.5 block text-xs text-ink-muted">
            Accept/reject flagged goods receipts with stock disposition
          </span>
        </Link>
      </section>
    </div>
  );
}
