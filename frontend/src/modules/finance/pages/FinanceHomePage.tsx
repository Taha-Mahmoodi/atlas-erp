/**
 * The finance module's own landing page (STRUCTURE §4: modules/finance/pages/). Links into
 * this slice's areas; AP/AR/statements/bank-rec/assets tiles land as those slices ship.
 */

import { Link } from "@tanstack/react-router";

const SECTIONS = [
  { to: "/finance/accounts", label: "Chart of Accounts", description: "Accounts and account groups" },
  { to: "/finance/journal-entries", label: "Journal Entries", description: "Draft, post, and reverse journal entries" },
  { to: "/finance/vendor-bills", label: "Vendor Bills", description: "Draft, post vendor bills" },
  { to: "/finance/vendor-payments", label: "Vendor Payments", description: "Pay vendor bills, clearing open items" },
  { to: "/finance/ap-aging", label: "AP Aging", description: "Open vendor bills by age" },
  { to: "/finance/customer-invoices", label: "Customer Invoices", description: "Draft, post customer invoices" },
  { to: "/finance/customer-receipts", label: "Customer Receipts", description: "Receive payment, clearing open items" },
  { to: "/finance/ar-aging", label: "AR Aging", description: "Open customer invoices by age" },
  { to: "/finance/dunning", label: "Dunning", description: "Advance reminder levels on overdue invoices" },
  { to: "/finance/trial-balance", label: "Trial Balance", description: "Every account's net debit/credit as of a date" },
  { to: "/finance/profit-loss", label: "Profit & Loss", description: "Revenue and expenses over a period" },
  { to: "/finance/balance-sheet", label: "Balance Sheet", description: "Assets, liabilities, and equity as of a date" },
  { to: "/finance/cash-flow", label: "Cash Flow Statement", description: "Indirect-method cash flow over a period" },
  { to: "/finance/bank-statements", label: "Bank Statements", description: "Import and reconcile bank statement lines" },
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
