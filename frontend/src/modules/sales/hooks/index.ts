/**
 * Sales hooks, split by sub-area (STRUCTURE §4) once the flat file crossed ~400 lines — same
 * threshold finance's, inventory's, and procurement's own hooks.ts split at. This barrel keeps
 * every existing `@/modules/sales/hooks` import working unchanged.
 */

export * from "@/modules/sales/hooks/customers";
export * from "@/modules/sales/hooks/orders";
export * from "@/modules/sales/hooks/pricing";
export * from "@/modules/sales/hooks/quotes";
