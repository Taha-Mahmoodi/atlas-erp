/**
 * Typed endpoint calls for the inventory module's item masters (STRUCTURE §4): item
 * categories, units of measure, items, UoM conversions. Warehouses/bins/moves/on-hand/
 * valuation and stock counts land in later slices of PLAN 15.5.
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  Item,
  ItemCategory,
  ItemCategoryCreate,
  ItemCategoryUpdate,
  ItemCreate,
  ItemType,
  ItemUpdate,
  Uom,
  UomConversion,
  UomConversionCreate,
  UomCreate,
  UomUpdate,
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
