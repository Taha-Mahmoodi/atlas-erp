/**
 * The tile/nav registry (PLAN 15.3): one entry per backend business module (STRUCTURE §3's
 * fixed module list), used to derive BOTH the role-based home page tiles and the sidebar nav
 * from the caller's permissions — no separate "menu config" to keep in sync. A module's UI
 * lands module-by-module (15.4-15.12); until then its route renders `ModulePlaceholderPage`.
 */

import type { IconName } from "@/components/Icon";

/** Module keys with a real static route registered in router.tsx (15.4+). ModuleLink.tsx
 * switches on this literal union so navigation stays type-safe as slices land — extend it
 * (and its switch in ModuleLink) one entry at a time, never widen to a bare `string`. */
export type StaticModuleRoute =
  | "finance"
  | "inventory"
  | "procurement"
  | "sales"
  | "reporting"
  | "admin"
  | "manufacturing"
  | "quality"
  | "maintenance"
  | "projects"
  | "crm"
  | "hr"
  | "hospitality";

export interface ModuleEntry {
  key: string;
  label: string;
  /** Permission-string prefix, e.g. "finance." — access is any permission starting with this. */
  permissionPrefix: string;
  description: string;
  /** Set once a module has a real static route — see shell/ModuleLink.tsx. Absent means the
   * dynamic `/$moduleKey` placeholder still covers it. */
  route?: StaticModuleRoute;
  /** Sidebar/palette glyph, from the in-house sprite (components/Icon). */
  icon: IconName;
  /** Which sidebar group this module belongs to — the section labels in the nav. */
  group: "Operations" | "Finance" | "People" | "Insights";
}

export const MODULES: ModuleEntry[] = [
  { key: "finance", label: "Finance", permissionPrefix: "finance.", description: "Journal, AP/AR, statements, bank rec, assets", route: "finance", icon: "dollar", group: "Finance" },
  { key: "inventory", label: "Inventory", permissionPrefix: "inventory.", description: "Items, stock, moves, counts", route: "inventory", icon: "box", group: "Operations" },
  { key: "procurement", label: "Procurement", permissionPrefix: "procurement.", description: "Vendors, requisitions, POs, receipts", route: "procurement", icon: "cart", group: "Operations" },
  { key: "sales", label: "Sales", permissionPrefix: "sales.", description: "Customers, quotes, orders, deliveries, invoices", route: "sales", icon: "tag", group: "Operations" },
  { key: "manufacturing", label: "Manufacturing", permissionPrefix: "manufacturing.", description: "BOMs, work centers, production, MRP", route: "manufacturing", icon: "factory", group: "Operations" },
  { key: "quality", label: "Quality", permissionPrefix: "quality.", description: "Inspection lots", route: "quality", icon: "shield-check", group: "Operations" },
  { key: "maintenance", label: "Maintenance", permissionPrefix: "maintenance.", description: "Equipment, maintenance orders", route: "maintenance", icon: "wrench", group: "Operations" },
  { key: "hospitality", label: "Hospitality", permissionPrefix: "hospitality.", description: "Menu availability, order tickets, kitchen display", route: "hospitality", icon: "utensils", group: "Operations" },
  { key: "hr", label: "HR", permissionPrefix: "hr.", description: "Employees, org chart, leave, time, payroll", route: "hr", icon: "users", group: "People" },
  { key: "projects", label: "Projects", permissionPrefix: "projects.", description: "WBS, cost reporting", route: "projects", icon: "layers", group: "People" },
  { key: "crm", label: "CRM", permissionPrefix: "crm.", description: "Leads, opportunities, activities", route: "crm", icon: "spark", group: "People" },
  { key: "reporting", label: "Reporting", permissionPrefix: "reporting.", description: "Dashboards, ad-hoc reports", route: "reporting", icon: "chart", group: "Insights" },
  // permissionPrefix was "core." pre-15.12 — a prefix no real permission key ever had (the
  // actual keys are admin.*), so the tile never showed; fixed alongside the route landing.
  { key: "admin", label: "Admin", permissionPrefix: "admin.", description: "Users, roles, audit, number sequences", route: "admin", icon: "gear", group: "Insights" },
];

/** Sidebar section order. A group with no permitted modules is skipped, never rendered empty. */
export const MODULE_GROUPS = ["Operations", "Finance", "People", "Insights"] as const;

export function modulesFor(permissions: string[]): ModuleEntry[] {
  return MODULES.filter((entry) =>
    permissions.some((permission) => permission.startsWith(entry.permissionPrefix)),
  );
}

export function moduleByKey(key: string): ModuleEntry | undefined {
  return MODULES.find((entry) => entry.key === key);
}
