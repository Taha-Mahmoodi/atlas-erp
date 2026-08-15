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

/** Background-job health (D-075): FAILED jobs in the last `window_days`. */
export interface FailedJobsKpi {
  count: number;
  window_days: number;
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
  failed_jobs?: FailedJobsKpi;
}

// --- Report builder (D-059) — mirrors the ReportSpec/ReportResult/catalog schemas -----------

export type ReportFilterOperator =
  | "eq"
  | "ne"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "in"
  | "like"
  | "between"
  | "is_null";

export type ReportAggregationFunc = "count" | "sum" | "avg" | "min" | "max";

export type ReportColumnType = "str" | "number" | "date" | "bool";

export interface ReportColumnDescriptor {
  name: string;
  label: string;
  type: ReportColumnType;
  filterable: boolean;
  groupable: boolean;
  is_aggregatable: boolean;
}

/** The entities-list endpoint already filters this catalog to the caller's role (D-059). */
export interface ReportEntityDescriptor {
  key: string;
  label: string;
  columns: ReportColumnDescriptor[];
}

export interface ReportEntityList {
  entities: ReportEntityDescriptor[];
}

/** Value shape depends on operator: scalar, list for IN, [low, high] for BETWEEN, bool for IS_NULL. */
export interface ReportFilter {
  column: string;
  operator: ReportFilterOperator;
  value?: unknown;
}

export interface ReportAggregation {
  column?: string | null;
  func: ReportAggregationFunc;
  alias?: string | null;
}

export interface ReportSpec {
  entity: string;
  columns?: string[];
  filters?: ReportFilter[];
  group_by?: string[];
  aggregations?: ReportAggregation[];
  limit?: number | null;
}

export interface ReportResult {
  /** The WIRE column names — also the keys of every row dict. Not display material (#166). */
  columns: string[];
  /**
   * The display header for each column, same order and length (#166). Optional here only so the
   * grid still renders against a pre-#166 server or a stale cached response; the current backend
   * always sends it. `resultHeaders` in `reporting/components/reportHeaders.ts` does the pairing.
   */
  column_labels?: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
}
