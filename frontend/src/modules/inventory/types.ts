/**
 * Mirrors backend `app/modules/inventory/schemas.py` (STRUCTURE §4). This slice covers item
 * masters only (categories, UoMs, items, UoM conversions) — warehouses/bins/moves/on-hand/
 * valuation and stock counts land in later slices of PLAN 15.5.
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
