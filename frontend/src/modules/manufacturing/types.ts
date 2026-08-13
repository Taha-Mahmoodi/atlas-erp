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
