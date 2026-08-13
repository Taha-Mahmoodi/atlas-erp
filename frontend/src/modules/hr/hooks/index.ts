/**
 * HR hooks, split by sub-area from day one (STRUCTURE §4; the sales/procurement hooks/
 * precedent) since the module ships in one PR: org core (10.1), leave (10.2), time (10.3),
 * payroll (10.4).
 */

export * from "@/modules/hr/hooks/leave";
export * from "@/modules/hr/hooks/org";
export * from "@/modules/hr/hooks/payroll";
export * from "@/modules/hr/hooks/time";
