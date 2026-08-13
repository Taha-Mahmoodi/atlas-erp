/**
 * The admin module's landing page (STRUCTURE §4). Sections are permission-gated per key
 * (not per module prefix) because admin spans several guards; tax codes and exchange
 * rates CROSS-LINK into finance's own settings pages, mirroring the backend's decision
 * to keep those APIs under /finance rather than duplicating them under /admin.
 */

import { Link } from "@tanstack/react-router";

import { useMe } from "@/lib/session";

const SECTIONS = [
  { to: "/admin/onboarding", label: "Tenant Onboarding", description: "Provision a new tenant from an industry template", permission: "onboarding.tenant.create" },
  { to: "/admin/users", label: "Users", description: "Create users and assign roles", permission: "admin.user.manage" },
  { to: "/admin/roles", label: "Roles", description: "Roles and their granted permissions", permission: "admin.role.manage" },
  { to: "/admin/audit-logs", label: "Audit Log", description: "Append-only change trail with before/after diffs", permission: "admin.audit.read" },
  { to: "/admin/number-sequences", label: "Number Sequences", description: "Per-tenant document numbering (read-only)", permission: "admin.numbering.read" },
  { to: "/finance/tax-codes", label: "Tax Codes", description: "Tax rates and GL wiring (finance settings)", permission: "finance.tax.read" },
  { to: "/finance/exchange-rates", label: "Exchange Rates", description: "Currency rates by date and type (finance settings)", permission: "finance.fx.manage" },
] as const;

export function AdminHomePage() {
  const me = useMe();
  const permissions = me.data?.permissions ?? [];
  const visible = SECTIONS.filter((section) => permissions.includes(section.permission));

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-xl font-semibold text-ink">Admin</h1>
      {!me.isPending && visible.length === 0 && (
        <p className="mt-6 text-sm text-ink-muted">
          You do not have any admin permissions. Ask an administrator for access.
        </p>
      )}
      <section className="mt-6 grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-4">
        {visible.map((section) => (
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
