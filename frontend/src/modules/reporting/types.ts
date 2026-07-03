/**
 * Mirrors backend `app/modules/reporting/schemas.py` (STRUCTURE §4: types.ts mirrors backend
 * schemas). snake_case kept as-is — no camelCase translation layer.
 */

export interface MoneyKpi {
  value: string;
  currency: string;
}

export interface AgingSummary {
  current: string;
  d30: string;
  d60: string;
  d90plus: string;
  total: string;
  currency: string;
}

export interface CountValueKpi {
  count: number;
  total: string;
  currency: string;
}

export interface OtdKpi {
  percent: number;
  on_time: number;
  total: number;
}

/** Every field is optional — the backend excludes KPIs the caller's role can't see (D-058). */
export interface DashboardResponse {
  cash_position?: MoneyKpi;
  ar_aging?: AgingSummary;
  ap_aging?: AgingSummary;
  inventory_value?: MoneyKpi;
  open_sales_orders?: CountValueKpi;
  open_purchase_orders?: CountValueKpi;
  otd_percent?: OtdKpi;
  wip_value?: MoneyKpi;
}
