/**
 * Inventory hooks, split by sub-area (STRUCTURE §4) once the flat file crossed ~400 lines —
 * same threshold finance's own hooks.ts split at. This barrel keeps every existing
 * `@/modules/inventory/hooks` import working unchanged.
 */

export * from "@/modules/inventory/hooks/counts";
export * from "@/modules/inventory/hooks/masters";
export * from "@/modules/inventory/hooks/stock";
export * from "@/modules/inventory/hooks/warehouses";
