/**
 * The finance module's own landing page (STRUCTURE §4: modules/finance/pages/). Links into
 * this slice's areas; AP/AR/statements/bank-rec/assets tiles land as those slices ship.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/finance/accounts", label: "Chart of Accounts", description: "Accounts and account groups" },
  { to: "/finance/journal-entries", label: "Journal Entries", description: "Draft, post, and reverse journal entries" },
] as const;

export function FinanceHomePage() {
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">Finance</h1>
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
