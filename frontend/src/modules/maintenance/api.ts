/**
 * Typed endpoint calls for the maintenance module (STRUCTURE §4): equipment register,
 * maintenance orders (+ schedule/start/complete/cancel lifecycle) and interval-based
 * preventive plans (+ activate/deactivate + the run-preventive generation). Create and
 * complete on orders and the preventive run are idempotent server-side (D-013).
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  CompleteOrderPayload,
  Equipment,
  EquipmentCreate,
  EquipmentStatus,
  EquipmentUpdate,
  MaintenanceOrder,
  MaintenanceOrderCreate,
  MaintenanceOrderStatus,
  MaintenanceOrderType,
  MaintenanceOrderUpdate,
  MaintenancePlan,
  MaintenancePlanCreate,
  MaintenancePlanStatus,
  MaintenancePlanUpdate,
  RunPreventiveResult,
  ScheduleOrderPayload,
} from "@/modules/maintenance/types";

// --- Equipment ----------------------------------------------------------------

export interface EquipmentFilters {
  cursor?: string;
  limit?: number;
  status?: EquipmentStatus;
}

export function listEquipment(filters: EquipmentFilters = {}): Promise<Page<Equipment>> {
  return api.get<Page<Equipment>>("/maintenance/equipment", { params: { ...filters } });
}

export function getEquipment(equipmentId: string): Promise<Equipment> {
  return api.get<Equipment>(`/maintenance/equipment/${equipmentId}`);
}

export function createEquipment(payload: EquipmentCreate): Promise<Equipment> {
  return api.post<Equipment>("/maintenance/equipment", payload);
}

export function updateEquipment(equipmentId: string, payload: EquipmentUpdate): Promise<Equipment> {
  return api.patch<Equipment>(`/maintenance/equipment/${equipmentId}`, payload);
}

// --- Maintenance orders -------------------------------------------------------

export interface MaintenanceOrderFilters {
  cursor?: string;
  limit?: number;
  equipment_id?: string;
  order_type?: MaintenanceOrderType;
  status?: MaintenanceOrderStatus;
}

export function listMaintenanceOrders(
  filters: MaintenanceOrderFilters = {},
): Promise<Page<MaintenanceOrder>> {
  return api.get<Page<MaintenanceOrder>>("/maintenance/maintenance-orders", {
    params: { ...filters },
  });
}

export function getMaintenanceOrder(orderId: string): Promise<MaintenanceOrder> {
  return api.get<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}`);
}

export function createMaintenanceOrder(payload: MaintenanceOrderCreate): Promise<MaintenanceOrder> {
  return api.post<MaintenanceOrder>("/maintenance/maintenance-orders", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function updateMaintenanceOrder(
  orderId: string,
  payload: MaintenanceOrderUpdate,
): Promise<MaintenanceOrder> {
  return api.patch<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}`, payload);
}

export function scheduleMaintenanceOrder(
  orderId: string,
  payload: ScheduleOrderPayload,
): Promise<MaintenanceOrder> {
  return api.post<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}/schedule`, payload);
}

export function startMaintenanceOrder(orderId: string): Promise<MaintenanceOrder> {
  return api.post<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}/start`, undefined);
}

export function completeMaintenanceOrder(
  orderId: string,
  payload: CompleteOrderPayload,
): Promise<MaintenanceOrder> {
  return api.post<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}/complete`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelMaintenanceOrder(orderId: string): Promise<MaintenanceOrder> {
  return api.post<MaintenanceOrder>(`/maintenance/maintenance-orders/${orderId}/cancel`, undefined);
}

// --- Maintenance plans --------------------------------------------------------

export interface MaintenancePlanFilters {
  cursor?: string;
  limit?: number;
  status?: MaintenancePlanStatus;
  equipment_id?: string;
}

export function listMaintenancePlans(
  filters: MaintenancePlanFilters = {},
): Promise<Page<MaintenancePlan>> {
  return api.get<Page<MaintenancePlan>>("/maintenance/maintenance-plans", {
    params: { ...filters },
  });
}

export function getMaintenancePlan(planId: string): Promise<MaintenancePlan> {
  return api.get<MaintenancePlan>(`/maintenance/maintenance-plans/${planId}`);
}

export function createMaintenancePlan(payload: MaintenancePlanCreate): Promise<MaintenancePlan> {
  return api.post<MaintenancePlan>("/maintenance/maintenance-plans", payload);
}

export function updateMaintenancePlan(
  planId: string,
  payload: MaintenancePlanUpdate,
): Promise<MaintenancePlan> {
  return api.patch<MaintenancePlan>(`/maintenance/maintenance-plans/${planId}`, payload);
}

export function activateMaintenancePlan(planId: string): Promise<MaintenancePlan> {
  return api.post<MaintenancePlan>(`/maintenance/maintenance-plans/${planId}/activate`, undefined);
}

export function deactivateMaintenancePlan(planId: string): Promise<MaintenancePlan> {
  return api.post<MaintenancePlan>(`/maintenance/maintenance-plans/${planId}/deactivate`, undefined);
}

export function runPreventiveMaintenance(): Promise<RunPreventiveResult> {
  return api.post<RunPreventiveResult>("/maintenance/maintenance-plans/run-preventive", undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}
