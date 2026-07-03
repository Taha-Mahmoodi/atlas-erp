/**
 * Mirrors backend `app/modules/inventory/schemas.py` (item masters), `stock_router.py` /
 * `valuation_router.py` (warehouses/bins/moves/on-hand/valuation), and `count_schemas.py`
 * (stock counts) (STRUCTURE §4).
 */

import type { Page } from "@/lib/apiClient";

export type CostingMethod = "MOVING_AVERAGE" | "FIFO";
export type ItemType = "STOCKED" | "NON_STOCKED" | "SERVICE";
export type TrackingMode = "NONE" | "LOT" | "SERIAL";

export interface ItemCategoryCreate {
  code: string;
  name: string;
  default_costing_method?: CostingMethod;
  inventory_account_id?: string | null;
  cogs_account_id?: string | null;
  price_difference_account_id?: string | null;
}

export type ItemCategoryUpdate = Partial<Omit<ItemCategoryCreate, "code">>;

export interface ItemCategory {
  id: string;
  code: string;
  name: string;
  default_costing_method: CostingMethod;
  inventory_account_id: string | null;
  cogs_account_id: string | null;
  price_difference_account_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface UomCreate {
  code: string;
  name: string;
}

export interface UomUpdate {
  name?: string;
}

export interface Uom {
  id: string;
  code: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface ItemCreate {
  item_code: string;
  name: string;
  description?: string | null;
  item_type: ItemType;
  category_id: string;
  base_uom_id: string;
  costing_method?: CostingMethod;
  tracking_mode?: TrackingMode;
  is_active?: boolean;
  reorder_point?: string | null;
  reorder_quantity?: string | null;
}

export type ItemUpdate = Partial<Omit<ItemCreate, "item_code" | "item_type">>;

export interface Item {
  id: string;
  item_code: string;
  name: string;
  description: string | null;
  item_type: ItemType;
  category_id: string;
  base_uom_id: string;
  costing_method: CostingMethod;
  tracking_mode: TrackingMode;
  is_active: boolean;
  reorder_point: string | null;
  reorder_quantity: string | null;
  created_at: string;
  updated_at: string;
}

/** 1 alt-UoM unit = factor_to_base × base-UoM units (e.g. base EA, alt BOX, factor 12). */
export interface UomConversionCreate {
  alt_uom_id: string;
  factor_to_base: string;
}

export interface UomConversion {
  id: string;
  item_id: string;
  alt_uom_id: string;
  factor_to_base: string;
  created_at: string;
}

// --- Warehouses / bins -------------------------------------------------------

export interface WarehouseCreate {
  code: string;
  name: string;
  is_active?: boolean;
}

export interface WarehouseUpdate {
  name?: string;
  is_active?: boolean;
}

export interface Warehouse {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** `is_default` marks a warehouse's default receiving bin — "exactly one default per
 * warehouse" is a service convention, not a DB constraint, so don't assume uniqueness. */
export interface BinCreate {
  warehouse_id: string;
  code: string;
  name: string;
  is_default?: boolean;
  is_active?: boolean;
}

export interface BinUpdate {
  name?: string;
  is_default?: boolean;
  is_active?: boolean;
}

export interface Bin {
  id: string;
  warehouse_id: string;
  code: string;
  name: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

// --- Stock moves (mirrors stock_router.py) -----------------------------------
//
// Immutable, posted at creation — no draft state, no edit/delete. Corrections are only via
// /reverse (a new opposite move). quantity is always positive; move_type decides which of
// from_bin_id/to_bin_id are populated, so direction is structural, not signed.

export type MoveType = "RECEIPT" | "ISSUE" | "TRANSFER" | "ADJUSTMENT";

export interface StockMoveCreate {
  move_type: MoveType;
  item_id: string;
  quantity: string;
  from_bin_id?: string | null;
  to_bin_id?: string | null;
  lot_id?: string | null;
  serial_id?: string | null;
  lot_code?: string | null;
  serial_code?: string | null;
  move_date?: string;
  reference?: string | null;
  /** Required on RECEIPT / positive ADJUSTMENT; ignored otherwise. */
  unit_cost?: string | null;
}

export interface StockMove {
  id: string;
  move_number: string;
  move_type: MoveType;
  item_id: string;
  quantity: string;
  base_uom_id: string;
  from_bin_id: string | null;
  to_bin_id: string | null;
  lot_id: string | null;
  serial_id: string | null;
  move_date: string;
  reference: string | null;
  posted: boolean;
  unit_cost: string | null;
  document_id: string;
  created_at: string;
}

// --- On-hand (maintained projection, not a live sum) -------------------------

export interface StockOnHand {
  item_id: string;
  bin_id: string;
  lot_id: string | null;
  on_hand_qty: string;
}

// --- Valuation ----------------------------------------------------------------
//
// StockValuation is only meaningful for MOVING_AVERAGE items; CostLayer only for FIFO items.
// Both per (item, warehouse) — valuation is not tracked per bin.

export interface StockValuation {
  item_id: string;
  warehouse_id: string;
  on_hand_qty: string;
  avg_unit_cost: string;
  total_value: string;
}

export interface CostLayer {
  id: string;
  item_id: string;
  warehouse_id: string;
  receipt_move_id: string;
  received_at: string;
  original_qty: string;
  remaining_qty: string;
  unit_cost: string;
  created_at: string;
}

// --- Stock counts (mirrors count_schemas.py) ---------------------------------
//
// Posting re-reads LIVE on-hand per line (not the stale creation-time snapshot) and posts one
// ordinary ADJUSTMENT move per non-zero variance through the same costing/event-bus pipeline
// every other move uses — finance posts the GL journal in the same transaction. No bespoke
// "count journal." POSTED is terminal (no un-post); CANCELLED only from DRAFT/COUNTING.

export type CountType = "PHYSICAL" | "CYCLE";
export type CountStatus = "DRAFT" | "COUNTING" | "POSTED" | "CANCELLED";

export interface StockCountCreate {
  count_type: CountType;
  warehouse_id: string;
  count_date?: string;
  description?: string | null;
  /** CYCLE only — ignored on PHYSICAL (a physical count is whole-warehouse). */
  item_ids?: string[];
  bin_ids?: string[];
}

export interface StockCount {
  id: string;
  count_number: string;
  count_type: CountType;
  warehouse_id: string;
  status: CountStatus;
  count_date: string;
  description: string | null;
  posted_at: string | null;
  document_id: string;
  created_at: string;
  updated_at: string;
}

export interface StockCountLineCountUpdate {
  counted_qty: string;
}

/** system_qty is the snapshot at creation/last-recount, not necessarily live — the variance
 * preview endpoint re-reads live on-hand for its own system_qty, which can differ. */
export interface StockCountLine {
  id: string;
  count_id: string;
  line_number: number;
  item_id: string;
  bin_id: string;
  lot_id: string | null;
  system_qty: string;
  counted_qty: string | null;
  variance_qty: string | null;
  adjustment_move_id: string | null;
  unit_cost: string | null;
}

export interface StockCountVarianceLine {
  line_id: string;
  item_id: string;
  bin_id: string;
  lot_id: string | null;
  system_qty: string;
  counted_qty: string | null;
  variance_qty: string | null;
  unit_cost: string;
  estimated_value_impact: string;
}

/** `lines` is keyset-paginated (#78 — a physical count routinely has thousands of lines), not
 * a plain array — `total_value_impact` is still the net impact over the WHOLE count, not just
 * this page. */
export interface StockCountVariancePreview {
  count_id: string;
  status: CountStatus;
  lines: Page<StockCountVarianceLine>;
  total_value_impact: string;
}
