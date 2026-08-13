/**
 * Manufacturing hooks, split by sub-area (STRUCTURE §4) once the flat file crossed ~400
 * lines — same threshold finance/inventory/sales split at. This barrel keeps every existing
 * `@/modules/manufacturing/hooks` import working unchanged.
 */

export * from "@/modules/manufacturing/hooks/masters";
export * from "@/modules/manufacturing/hooks/mrp";
export * from "@/modules/manufacturing/hooks/production";
