/**
 * The tile/nav registry (PLAN 15.3): one entry per backend business module (STRUCTURE §3's
 * fixed module list), used to derive BOTH the role-based home page tiles and the sidebar nav
 * from the caller's permissions — no separate "menu config" to keep in sync. A module's UI
 * lands module-by-module (15.4-15.12); until then its route renders `ModulePlaceholderPage`.
 */

export interface ModuleEntry {
  key: string;
  label: string;
  /** Permission-string prefix, e.g. "finance." — access is any permission starting with this. */
  permissionPrefix: string;
  description: string;
}

export const MODULES: ModuleEntry[] = [
  { key: "finance", label: "Finance", permissionPrefix: "finance.", description: "Journal, AP/AR, statements, bank rec, assets" },
  { key: "inventory", label: "Inventory", permissionPrefix: "inventory.", description: "Items, stock, moves, counts" },
  { key: "procurement", label: "Procurement", permissionPrefix: "procurement.", description: "Vendors, requisitions, POs, receipts" },
  { key: "sales", label: "Sales", permissionPrefix: "sales.", description: "Customers, quotes, orders, deliveries, invoices" },
  { key: "manufacturing", label: "Manufacturing", permissionPrefix: "manufacturing.", description: "BOMs, work centers, production, MRP" },
  { key: "quality", label: "Quality", permissionPrefix: "quality.", description: "Inspection lots" },
  { key: "maintenance", label: "Maintenance", permissionPrefix: "maintenance.", description: "Equipment, maintenance orders" },
  { key: "hr", label: "HR", permissionPrefix: "hr.", description: "Employees, org chart, leave, time, payroll" },
  { key: "projects", label: "Projects", permissionPrefix: "projects.", description: "WBS, cost reporting" },
  { key: "crm", label: "CRM", permissionPrefix: "crm.", description: "Leads, opportunities, activities" },
  { key: "reporting", label: "Reporting", permissionPrefix: "reporting.", description: "Dashboards, ad-hoc reports" },
  { key: "admin", label: "Admin", permissionPrefix: "core.", description: "Users, roles, audit, number sequences" },
];

export function modulesFor(permissions: string[]): ModuleEntry[] {
  return MODULES.filter((entry) =>
    permissions.some((permission) => permission.startsWith(entry.permissionPrefix)),
  );
}

export function moduleByKey(key: string): ModuleEntry | undefined {
  return MODULES.find((entry) => entry.key === key);
}
