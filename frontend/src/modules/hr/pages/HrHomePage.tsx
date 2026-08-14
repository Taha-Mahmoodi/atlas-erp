/**
 * The HR module's own landing page (STRUCTURE §4: modules/hr/pages/). PLAN 15.10 — employees
 * (masked compensation), departments + positions + org chart, leave, time tracking, payroll.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/hr/employees", label: "Employees", description: "Employee master; compensation masked by RBAC" },
  { to: "/hr/departments", label: "Departments", description: "Department tree with cost-center links" },
  { to: "/hr/positions", label: "Positions", description: "Position catalog per department" },
  { to: "/hr/org-chart", label: "Org Chart", description: "The reporting tree" },
  { to: "/hr/leave-types", label: "Leave Types", description: "Accrual rules per leave type" },
  { to: "/hr/leave-balances", label: "Leave Balances", description: "Per-employee balances and the accrual run" },
  { to: "/hr/leave-requests", label: "Leave Requests", description: "Request and approval flow" },
  { to: "/hr/timesheets", label: "Timesheets", description: "Time entries with project/cost-center allocation" },
  { to: "/hr/time-allocation", label: "Time Allocation", description: "Approved hours by cost center or project" },
  { to: "/hr/payroll-runs", label: "Payroll Runs", description: "Flat-tax gross-to-net; posts a finance journal" },
] as const;

export function HrHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">HR</h1>
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
