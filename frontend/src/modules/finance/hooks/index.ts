/**
 * Finance hooks, split by sub-area (STRUCTURE §4) once the flat file crossed ~400 lines —
 * same threshold the backend itself splits router.py/service.py at. This barrel keeps every
 * existing `@/modules/finance/hooks` import working unchanged.
 */

export * from "@/modules/finance/hooks/accounts";
export * from "@/modules/finance/hooks/assets";
export * from "@/modules/finance/hooks/bank";
export * from "@/modules/finance/hooks/journal-entries";
export * from "@/modules/finance/hooks/payables";
export * from "@/modules/finance/hooks/receivables";
export * from "@/modules/finance/hooks/reference";
export * from "@/modules/finance/hooks/statements";
