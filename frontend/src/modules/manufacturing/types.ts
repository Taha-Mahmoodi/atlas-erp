/**
 * Mirrors backend `app/modules/manufacturing/schemas/*.py` (STRUCTURE §4). Slice 1/3 of PLAN
 * 15.8: master data (work centers, BOMs, routings). Production orders and MRP land in later
 * slices. No idempotency keys anywhere in this slice (D-013) — masters carry no gapless
 * number and no idempotency key (D-047), unlike production orders/MRP which do.
 *
 * A BOM/routing's identity is `(item_id, version)`, NOT an auto-numbered code — `version` is
 * client-supplied (e.g. "1", "REV-A"). `is_default` is distinct from `status`: activating a
 * version sets `is_default=true` AND demotes any prior ACTIVE+is_default version for the SAME
 * item to `is_default=false` in the same transaction (their status stays ACTIVE, only the flag
 * flips) — so at most one (ACTIVE, is_default) version exists per item at a time. Deactivating
 * clears both status->INACTIVE and is_default->false. Only DRAFT is editable; components/
 * operations can only be added/removed while the header is DRAFT.
 */

export interface WorkCenter {
  id: string;
  code: string;
  name: string;
  description: string | null;
  cost_center_id: string | null;
  capacity_hours_per_day: string;
  efficiency_percent: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkCenterCreate {
  code: string;
  name: string;
  description?: string | null;
  cost_center_id?: string | null;
  capacity_hours_per_day?: string;
  efficiency_percent?: string;
  is_active?: boolean;
}

export type WorkCenterUpdate = Omit<WorkCenterCreate, "code">;

// --- BOMs ---------------------------------------------------------------------------

export type BomStatus = "DRAFT" | "ACTIVE" | "INACTIVE";

export interface Bom {
  id: string;
  item_id: string;
  version: string;
  name: string;
  status: BomStatus;
  base_quantity: string;
  uom_id: string;
  is_default: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface BomCreate {
  item_id: string;
  version: string;
  name: string;
  base_quantity?: string;
  uom_id: string;
  notes?: string | null;
}

// DRAFT-only; item_id/version/status/is_default are immutable or action-only.
export type BomUpdate = Pick<BomCreate, "name" | "base_quantity" | "uom_id" | "notes">;

export interface BomComponent {
  id: string;
  bom_id: string;
  line_number: number;
  component_item_id: string;
  quantity_per: string;
  uom_id: string;
  scrap_percent: string;
  notes: string | null;
  created_at: string;
}

export interface BomComponentCreate {
  component_item_id: string;
  quantity_per: string;
  uom_id: string;
  scrap_percent?: string;
  // Omit to have the server append the next line number (by 10s); supply to pick a specific slot.
  line_number?: number | null;
  notes?: string | null;
}

// --- Routings -------------------------------------------------------------------------

export type RoutingStatus = "DRAFT" | "ACTIVE" | "INACTIVE";

export interface Routing {
  id: string;
  item_id: string;
  version: string;
  name: string;
  status: RoutingStatus;
  is_default: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface RoutingCreate {
  item_id: string;
  version: string;
  name: string;
  notes?: string | null;
}

export type RoutingUpdate = Pick<RoutingCreate, "name" | "notes">;

export interface RoutingOperation {
  id: string;
  routing_id: string;
  operation_number: number;
  work_center_id: string;
  description: string | null;
  setup_time_minutes: string;
  run_time_minutes_per_unit: string;
  notes: string | null;
  created_at: string;
}

export interface RoutingOperationCreate {
  work_center_id: string;
  description?: string | null;
  setup_time_minutes?: string;
  run_time_minutes_per_unit?: string;
  // Omit to have the server append the next operation number (by 10s); supply to pick a slot.
  operation_number?: number | null;
  notes?: string | null;
}

// --- Production orders ----------------------------------------------------------------
// Mirrors schemas/production.py (PLAN 8.2, D-048). A production order IS a numbered document
// (MO-…): create explodes the item's ACTIVE default BOM into reserved component rows and
// snapshots the routing — components/operations are SERVER-DERIVED, never posted. Status is
// server-driven: DRAFT → (release) RELEASED → (issue) IN_PROGRESS → (finish) FINISHED;
// CANCELLED only from DRAFT/RELEASED (once components are issued the order must be finished).

export type ProductionOrderStatus = "DRAFT" | "RELEASED" | "IN_PROGRESS" | "FINISHED" | "CANCELLED";

export interface ProductionOrder {
  id: string;
  order_number: string;
  status: ProductionOrderStatus;
  item_id: string;
  quantity: string;
  bom_id: string;
  routing_id: string | null;
  warehouse_id: string;
  planned_start_date: string | null;
  planned_end_date: string | null;
  finished_quantity: string;
  accumulated_wip_cost: string;
  notes: string | null;
  released_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProductionOrderComponent {
  id: string;
  production_order_id: string;
  line_number: number;
  component_item_id: string;
  required_quantity: string;
  issued_quantity: string;
  uom_id: string;
  bin_id: string;
}

export interface ProductionOrderOperation {
  id: string;
  production_order_id: string;
  operation_number: number;
  work_center_id: string;
  description: string | null;
  setup_time_minutes: string;
  run_time_minutes_per_unit: string;
  planned_minutes: string;
}

export interface ProductionOrderDetail extends ProductionOrder {
  components: ProductionOrderComponent[];
  operations: ProductionOrderOperation[];
}

export interface ProductionOrderCreate {
  item_id: string;
  quantity: string;
  warehouse_id: string;
  // Omit to resolve the item's ACTIVE default BOM/routing (422 manufacturing.no_active_bom
  // when the item has no active default BOM and none is supplied; routingless is allowed).
  bom_id?: string | null;
  routing_id?: string | null;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
  notes?: string | null;
}

export interface ComponentIssueLine {
  component_line_number: number;
  quantity: string;
  bin_id?: string | null;
  lot_code?: string | null;
  serial_code?: string | null;
}

export interface IssueComponentsRequest {
  // Omit/empty = issue each component's full remaining required quantity from its default bin.
  lines?: ComponentIssueLine[] | null;
  move_date?: string | null;
}

export interface FinishOrderRequest {
  finished_quantity: string;
  finished_bin_id: string;
  lot_code?: string | null;
  serial_code?: string | null;
  move_date?: string | null;
}

// --- MRP ------------------------------------------------------------------------------
// Mirrors schemas/mrp.py (PLAN 8.3, D-049). The RUN always executes as a background job:
// POST /mrp/runs returns 202 JobSubmitted for /jobs polling (lib/jobs), the job result
// carries {run_id}. Planned orders are the run's regenerated planning output (PLANNED →
// FIRMED/CONVERTED/CANCELLED); capacity loads are the rough-capacity check per work center.

export type MrpRunStatus = "RUNNING" | "COMPLETED" | "FAILED";
export type PlannedOrderType = "MAKE" | "BUY";
export type PlannedOrderStatus = "PLANNED" | "FIRMED" | "CONVERTED" | "CANCELLED";

export interface MrpRun {
  id: string;
  run_number: string;
  status: MrpRunStatus;
  run_date: string;
  horizon_days: number;
  warehouse_id: string | null;
  demand_source: string | null;
  planned_make_count: number;
  planned_buy_count: number;
  notes: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CapacityLoad {
  id: string;
  mrp_run_id: string;
  work_center_id: string;
  planned_load_minutes: string;
  available_minutes: string;
  utilization_percent: string;
  is_overloaded: boolean;
}

export interface MrpRunSummary extends MrpRun {
  capacity_loads: CapacityLoad[];
}

export interface PlannedOrder {
  id: string;
  mrp_run_id: string;
  item_id: string;
  order_type: PlannedOrderType;
  quantity: string;
  due_date: string | null;
  status: PlannedOrderStatus;
  source_notes: string | null;
  level: number;
  converted_document_id: string | null;
  created_at: string;
}

export interface MrpRunRequest {
  run_date?: string | null;
  horizon_days?: number | null;
  warehouse_id?: string | null;
}

export interface PlannedOrderConvertRequest {
  // Required for a MAKE order whose run had no warehouse scope; ignored for BUY.
  warehouse_id?: string | null;
}
