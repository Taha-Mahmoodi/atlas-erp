/**
 * The menu-structure endpoints (#212, D-081): the section tree, a dish's placement in it, and the
 * tags in use.
 *
 * A sibling of `api.ts` rather than more of it, mirroring the backend's third router: this is the
 * property SETTING UP its menu — slow-changing structure a manager edits — while `api.ts` is the
 * floor mid-service.
 *
 * No idempotency keys: nothing here creates a document or claims a number, and the placement write
 * is a PUT that replaces the dish's whole menu placement, so a retry is the same state.
 */

import { api } from "@/lib/apiClient";
import type {
  MenuPlacement,
  MenuPlacementSet,
  MenuSection,
  MenuSectionCreate,
  MenuSectionUpdate,
} from "@/modules/hospitality/types";

export function listSections(): Promise<MenuSection[]> {
  return api.get<MenuSection[]>("/hospitality/menu/sections");
}

export function createSection(payload: MenuSectionCreate): Promise<MenuSection> {
  return api.post<MenuSection>("/hospitality/menu/sections", payload);
}

export function updateSection(
  sectionId: string,
  payload: MenuSectionUpdate,
): Promise<MenuSection> {
  return api.patch<MenuSection>(`/hospitality/menu/sections/${sectionId}`, payload);
}

/** Refused while dishes or sub-sections still hang off it (409 `menu_section_not_empty`) — the
 * backend does not cascade, so the UI surfaces the refusal rather than pre-empting it. */
export function deleteSection(sectionId: string): Promise<void> {
  return api.delete<void>(`/hospitality/menu/sections/${sectionId}`);
}

/** Every placed or tagged dish. Unpaginated by contract: the answer is bounded by the number of
 * dishes a kitchen cooks, and a map split across pages is one the caller has to reassemble. */
export function listPlacements(): Promise<{ items: MenuPlacement[] }> {
  return api.get<{ items: MenuPlacement[] }>("/hospitality/menu/placements");
}

export function listTags(): Promise<string[]> {
  return api.get<string[]>("/hospitality/menu/tags");
}

/** Section and tags REPLACED together — they are edited on one row, and a half-applied edit is
 * the failure a manager would have to unpick by hand. */
export function setPlacement(
  itemId: string,
  payload: MenuPlacementSet,
): Promise<MenuPlacement> {
  return api.put<MenuPlacement>(`/hospitality/menu/${itemId}/placement`, payload);
}
