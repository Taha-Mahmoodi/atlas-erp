/**
 * The CRM module's own landing page (STRUCTURE §4: modules/crm/pages/). PLAN 15.11: leads →
 * opportunities kanban, activities, and the convert-to-customer+quote door into sales.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/crm/leads", label: "Leads", description: "Capture, qualify and convert into opportunities" },
  { to: "/crm/opportunities", label: "Pipeline", description: "The opportunity kanban — drag deals between stages" },
  { to: "/crm/activities", label: "Activities", description: "Calls, emails, meetings and tasks across the pipeline" },
] as const;

export function CrmHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">CRM</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Won opportunities convert into a real sales customer and quote in one action.
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
