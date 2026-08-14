/**
 * The projects module's own landing page (STRUCTURE §4: modules/projects/pages/). PLAN 15.11:
 * projects + WBS cost collectors + the per-project cost report (opened from a project).
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/projects/list", label: "Projects", description: "Project masters, WBS structure and status" },
] as const;

export function ProjectsHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">Projects</h1>
      <p className="mt-1 text-[13px] text-ink-muted">
        WBS elements are the costing objects finance journal lines and HR time entries post to;
        each project's cost report projects those actuals against budget.
      </p>
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
