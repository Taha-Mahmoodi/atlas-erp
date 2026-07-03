/**
 * Typed endpoint calls for the inventory module (STRUCTURE §4): item masters, warehouses/
 * bins, stock moves, on-hand, valuation, stock counts.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type { JobSubmitted } from "@/lib/jobs";
import type {
  Bin,
  BinCreate,
  BinUpdate,
  CostLayer,
  CountType,
  Item,
  ItemCategory,
  ItemCategoryCreate,
  ItemCategoryUpdate,
  ItemCreate,
  ItemType,
  ItemUpdate,
  MoveType,
  StockCount,
  StockCountCreate,
  StockCountLine,
  StockCountLineCountUpdate,
  StockCountVariancePreview,
  StockMove,
  StockMoveCreate,
  StockOnHand,
  StockValuation,
  Uom,
  UomConversion,
  UomConversionCreate,
  UomCreate,
  UomUpdate,
  Warehouse,
  WarehouseCreate,
  WarehouseUpdate,
} from "@/modules/inventory/types";

export interface ItemCategoryFilters {
  cursor?: string;
  limit?: number;
}

export function listItemCategories(
  filters: ItemCategoryFilters = {},
): Promise<Page<ItemCategory>> {
  return api.get<Page<ItemCategory>>("/inventory/item-categories", { params: { ...filters } });
}

export function getItemCategory(categoryId: string): Promise<ItemCategory> {
  return api.get<ItemCategory>(`/inventory/item-categories/${categoryId}`);
}

export function createItemCategory(payload: ItemCategoryCreate): Promise<ItemCategory> {
  return api.post<ItemCategory>("/inventory/item-categories", payload);
}

export function updateItemCategory(
  categoryId: string,
  payload: ItemCategoryUpdate,
): Promise<ItemCategory> {
  return api.patch<ItemCategory>(`/inventory/item-categories/${categoryId}`, payload);
}

export interface UomFilters {
  cursor?: string;
  limit?: number;
}

export function listUoms(filters: UomFilters = {}): Promise<Page<Uom>> {
  return api.get<Page<Uom>>("/inventory/uoms", { params: { ...filters } });
}

export function getUom(uomId: string): Promise<Uom> {
  return api.get<Uom>(`/inventory/uoms/${uomId}`);
}

export function createUom(payload: UomCreate): Promise<Uom> {
  return api.post<Uom>("/inventory/uoms", payload);
}

export function updateUom(uomId: string, payload: UomUpdate): Promise<Uom> {
  return api.patch<Uom>(`/inventory/uoms/${uomId}`, payload);
}

export interface ItemFilters {
  cursor?: string;
  limit?: number;
  item_type?: ItemType;
  category_id?: string;
  is_active?: boolean;
}

export function listItems(filters: ItemFilters = {}): Promise<Page<Item>> {
  return api.get<Page<Item>>("/inventory/items", { params: { ...filters } });
}

export function getItem(itemId: string): Promise<Item> {
  return api.get<Item>(`/inventory/items/${itemId}`);
}

export function createItem(payload: ItemCreate): Promise<Item> {
  return api.post<Item>("/inventory/items", payload);
}

export function updateItem(itemId: string, payload: ItemUpdate): Promise<Item> {
  return api.patch<Item>(`/inventory/items/${itemId}`, payload);
}

export function listUomConversions(itemId: string): Promise<UomConversion[]> {
  return api.get<UomConversion[]>(`/inventory/items/${itemId}/uom-conversions`);
}

export function createUomConversion(
  itemId: string,
  payload: UomConversionCreate,
): Promise<UomConversion> {
  return api.post<UomConversion>(`/inventory/items/${itemId}/uom-conversions`, payload);
}

// --- Warehouses / bins --------------------------------------------------------

export interface WarehouseFilters {
  cursor?: string;
  limit?: number;
}

export function listWarehouses(filters: WarehouseFilters = {}): Promise<Page<Warehouse>> {
  return api.get<Page<Warehouse>>("/inventory/warehouses", { params: { ...filters } });
}

export function getWarehouse(warehouseId: string): Promise<Warehouse> {
  return api.get<Warehouse>(`/inventory/warehouses/${warehouseId}`);
}

export function createWarehouse(payload: WarehouseCreate): Promise<Warehouse> {
  return api.post<Warehouse>("/inventory/warehouses", payload);
}

export function updateWarehouse(warehouseId: string, payload: WarehouseUpdate): Promise<Warehouse> {
  return api.patch<Warehouse>(`/inventory/warehouses/${warehouseId}`, payload);
}

export interface BinFilters {
  cursor?: string;
  limit?: number;
  warehouse_id?: string;
}

export function listBins(filters: BinFilters = {}): Promise<Page<Bin>> {
  return api.get<Page<Bin>>("/inventory/bins", { params: { ...filters } });
}

export function getBin(binId: string): Promise<Bin> {
  return api.get<Bin>(`/inventory/bins/${binId}`);
}

export function createBin(payload: BinCreate): Promise<Bin> {
  return api.post<Bin>("/inventory/bins", payload);
}

export function updateBin(binId: string, payload: BinUpdate): Promise<Bin> {
  return api.patch<Bin>(`/inventory/bins/${binId}`, payload);
}

// --- Stock moves ---------------------------------------------------------------

export function createStockMove(payload: StockMoveCreate): Promise<StockMove> {
  return api.post<StockMove>("/inventory/stock-moves", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function reverseStockMove(moveId: string): Promise<StockMove> {
  return api.post<StockMove>(`/inventory/stock-moves/${moveId}/reverse`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export interface StockMoveFilters {
  cursor?: string;
  limit?: number;
  item_id?: string;
  bin_id?: string;
  move_type?: MoveType;
  date_from?: string;
  date_to?: string;
}

export function listStockMoves(filters: StockMoveFilters = {}): Promise<Page<StockMove>> {
  return api.get<Page<StockMove>>("/inventory/stock-moves", { params: { ...filters } });
}

export function getStockMove(moveId: string): Promise<StockMove> {
  return api.get<StockMove>(`/inventory/stock-moves/${moveId}`);
}

// --- On-hand -------------------------------------------------------------------

export interface StockOnHandFilters {
  cursor?: string;
  limit?: number;
  item_id?: string;
  bin_id?: string;
}

export function listStockOnHand(filters: StockOnHandFilters = {}): Promise<Page<StockOnHand>> {
  return api.get<Page<StockOnHand>>("/inventory/stock-on-hand", { params: { ...filters } });
}

// --- Valuation -------------------------------------------------------------------

export interface StockValuationFilters {
  cursor?: string;
  limit?: number;
  item_id?: string;
  warehouse_id?: string;
}

export function listStockValuations(
  filters: StockValuationFilters = {},
): Promise<Page<StockValuation>> {
  return api.get<Page<StockValuation>>("/inventory/stock-valuations", { params: { ...filters } });
}

export function listCostLayers(
  itemId: string,
  filters: { cursor?: string; limit?: number; warehouse_id?: string; include_exhausted?: boolean } = {},
): Promise<Page<CostLayer>> {
  return api.get<Page<CostLayer>>(`/inventory/items/${itemId}/cost-layers`, {
    params: { ...filters },
  });
}

// --- Stock counts --------------------------------------------------------------

export function createStockCount(payload: StockCountCreate): Promise<StockCount> {
  return api.post<StockCount>("/inventory/stock-counts", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export interface StockCountFilters {
  cursor?: string;
  limit?: number;
  status?: string;
  warehouse_id?: string;
  count_type?: CountType;
}

export function listStockCounts(filters: StockCountFilters = {}): Promise<Page<StockCount>> {
  return api.get<Page<StockCount>>("/inventory/stock-counts", { params: { ...filters } });
}

export function getStockCount(countId: string): Promise<StockCount> {
  return api.get<StockCount>(`/inventory/stock-counts/${countId}`);
}

export function listStockCountLines(
  countId: string,
  filters: { cursor?: string; limit?: number } = {},
): Promise<Page<StockCountLine>> {
  return api.get<Page<StockCountLine>>(`/inventory/stock-counts/${countId}/lines`, {
    params: { ...filters },
  });
}

export function getStockCountVariancePreview(
  countId: string,
  filters: { cursor?: string; limit?: number } = {},
): Promise<StockCountVariancePreview> {
  return api.get<StockCountVariancePreview>(`/inventory/stock-counts/${countId}/variance-preview`, {
    params: { ...filters },
  });
}

export function recordCountedQuantity(
  countId: string,
  lineId: string,
  payload: StockCountLineCountUpdate,
): Promise<StockCountLine> {
  return api.post<StockCountLine>(
    `/inventory/stock-counts/${countId}/lines/${lineId}/count`,
    payload,
  );
}

/** Resolves to either the finished count (small variance count, 200) or a job to poll (large
 * count, PERFORMANCE §3, 202) — the caller distinguishes by checking for `job_id`. */
export function postStockCount(countId: string): Promise<StockCount | JobSubmitted> {
  return api.post<StockCount | JobSubmitted>(`/inventory/stock-counts/${countId}/post`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelStockCount(countId: string): Promise<StockCount> {
  return api.post<StockCount>(`/inventory/stock-counts/${countId}/cancel`, undefined);
}
