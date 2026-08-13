/**
 * Typed endpoint calls for the manufacturing module (STRUCTURE §4): work centers, BOMs +
 * components, routings + operations. Slice 1 of PLAN 15.8. No idempotency keys anywhere in
 * this slice (D-013/D-047) — masters carry no gapless number, unlike production orders/MRP.
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  Bom,
  BomComponent,
  BomComponentCreate,
  BomCreate,
  BomStatus,
  BomUpdate,
  Routing,
  RoutingCreate,
  RoutingOperation,
  RoutingOperationCreate,
  RoutingStatus,
  RoutingUpdate,
  WorkCenter,
  WorkCenterCreate,
  WorkCenterUpdate,
} from "@/modules/manufacturing/types";

export interface WorkCenterFilters {
  cursor?: string;
  limit?: number;
  is_active?: boolean;
}

export function listWorkCenters(filters: WorkCenterFilters = {}): Promise<Page<WorkCenter>> {
  return api.get<Page<WorkCenter>>("/manufacturing/work-centers", { params: { ...filters } });
}

export function getWorkCenter(workCenterId: string): Promise<WorkCenter> {
  return api.get<WorkCenter>(`/manufacturing/work-centers/${workCenterId}`);
}

export function createWorkCenter(payload: WorkCenterCreate): Promise<WorkCenter> {
  return api.post<WorkCenter>("/manufacturing/work-centers", payload);
}

export function updateWorkCenter(workCenterId: string, payload: WorkCenterUpdate): Promise<WorkCenter> {
  return api.patch<WorkCenter>(`/manufacturing/work-centers/${workCenterId}`, payload);
}

// --- BOMs ---------------------------------------------------------------------------

export interface BomFilters {
  cursor?: string;
  limit?: number;
  item_id?: string;
  status?: BomStatus;
}

export function listBoms(filters: BomFilters = {}): Promise<Page<Bom>> {
  return api.get<Page<Bom>>("/manufacturing/boms", { params: { ...filters } });
}

export function getBom(bomId: string): Promise<Bom> {
  return api.get<Bom>(`/manufacturing/boms/${bomId}`);
}

export function createBom(payload: BomCreate): Promise<Bom> {
  return api.post<Bom>("/manufacturing/boms", payload);
}

export function updateBom(bomId: string, payload: BomUpdate): Promise<Bom> {
  return api.patch<Bom>(`/manufacturing/boms/${bomId}`, payload);
}

export function activateBom(bomId: string): Promise<Bom> {
  return api.post<Bom>(`/manufacturing/boms/${bomId}/activate`, undefined);
}

export function deactivateBom(bomId: string): Promise<Bom> {
  return api.post<Bom>(`/manufacturing/boms/${bomId}/deactivate`, undefined);
}

export function listBomComponents(bomId: string): Promise<BomComponent[]> {
  return api.get<BomComponent[]>(`/manufacturing/boms/${bomId}/components`);
}

export function createBomComponent(bomId: string, payload: BomComponentCreate): Promise<BomComponent> {
  return api.post<BomComponent>(`/manufacturing/boms/${bomId}/components`, payload);
}

export function deleteBomComponent(bomId: string, componentId: string): Promise<void> {
  return api.delete<void>(`/manufacturing/boms/${bomId}/components/${componentId}`);
}

// --- Routings -------------------------------------------------------------------------

export interface RoutingFilters {
  cursor?: string;
  limit?: number;
  item_id?: string;
  status?: RoutingStatus;
}

export function listRoutings(filters: RoutingFilters = {}): Promise<Page<Routing>> {
  return api.get<Page<Routing>>("/manufacturing/routings", { params: { ...filters } });
}

export function getRouting(routingId: string): Promise<Routing> {
  return api.get<Routing>(`/manufacturing/routings/${routingId}`);
}

export function createRouting(payload: RoutingCreate): Promise<Routing> {
  return api.post<Routing>("/manufacturing/routings", payload);
}

export function updateRouting(routingId: string, payload: RoutingUpdate): Promise<Routing> {
  return api.patch<Routing>(`/manufacturing/routings/${routingId}`, payload);
}

export function activateRouting(routingId: string): Promise<Routing> {
  return api.post<Routing>(`/manufacturing/routings/${routingId}/activate`, undefined);
}

export function deactivateRouting(routingId: string): Promise<Routing> {
  return api.post<Routing>(`/manufacturing/routings/${routingId}/deactivate`, undefined);
}

export function listRoutingOperations(routingId: string): Promise<RoutingOperation[]> {
  return api.get<RoutingOperation[]>(`/manufacturing/routings/${routingId}/operations`);
}

export function createRoutingOperation(
  routingId: string,
  payload: RoutingOperationCreate,
): Promise<RoutingOperation> {
  return api.post<RoutingOperation>(`/manufacturing/routings/${routingId}/operations`, payload);
}

export function deleteRoutingOperation(routingId: string, operationId: string): Promise<void> {
  return api.delete<void>(`/manufacturing/routings/${routingId}/operations/${operationId}`);
}
