/**
 * Mirrors backend `app/modules/inventory/schemas.py` (item masters) and `stock_router.py` /
 * `valuation_router.py` (warehouses/bins/moves/on-hand/valuation) (STRUCTURE §4). Stock
 * counts land in a later slice of PLAN 15.5.
 */

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
