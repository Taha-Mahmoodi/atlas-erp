/**
 * The tile/nav registry (PLAN 15.3): one entry per backend business module (STRUCTURE §3's
 * fixed module list), used to derive BOTH the role-based home page tiles and the sidebar nav
 * from the caller's permissions — no separate "menu config" to keep in sync. A module's UI
 * lands module-by-module (15.4-15.12); until then its route renders `ModulePlaceholderPage`.
 */

/** Module keys with a real static route registered in router.tsx (15.4+). ModuleLink.tsx
 * switches on this literal union so navigation stays type-safe as slices land — extend it
 * (and its switch in ModuleLink) one entry at a time, never widen to a bare `string`. */
export type StaticModuleRoute = "finance" | "inventory";

export interface ModuleEntry {
  key: string;
  label: string;
  /** Permission-string prefix, e.g. "finance." — access is any permission starting with this. */
  permissionPrefix: string;
  description: string;
  /** Set once a module has a real static route — see shell/ModuleLink.tsx. Absent means the
   * dynamic `/$moduleKey` placeholder still covers it. */
  route?: StaticModuleRoute;
}

export const MODULES: ModuleEntry[] = [
  { key: "finance", label: "Finance", permissionPrefix: "finance.", description: "Journal, AP/AR, statements, bank rec, assets", route: "finance" },
  { key: "inventory", label: "Inventory", permissionPrefix: "inventory.", description: "Items, stock, moves, counts", route: "inventory" },
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
