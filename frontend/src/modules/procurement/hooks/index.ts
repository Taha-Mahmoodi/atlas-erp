/**
 * Procurement hooks, split by sub-area (STRUCTURE §4) once the flat file crossed ~400 lines —
 * same threshold finance's and inventory's own hooks.ts split at. This barrel keeps every
 * existing `@/modules/procurement/hooks` import working unchanged.
 */

export * from "@/modules/procurement/hooks/approvalRules";
export * from "@/modules/procurement/hooks/goodsReceipts";
export * from "@/modules/procurement/hooks/orders";
export * from "@/modules/procurement/hooks/requisitions";
export * from "@/modules/procurement/hooks/rfqs";
export * from "@/modules/procurement/hooks/vendors";
