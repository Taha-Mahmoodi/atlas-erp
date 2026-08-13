/**
 * TanStack Query hooks for the maintenance module (STRUCTURE §4). Flat file — under the
 * ~400-line threshold the bigger modules split at.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activateMaintenancePlan,
  cancelMaintenanceOrder,
  completeMaintenanceOrder,
  createEquipment,
  createMaintenanceOrder,
  createMaintenancePlan,
  deactivateMaintenancePlan,
  getEquipment,
  getMaintenanceOrder,
  getMaintenancePlan,
  listEquipment,
  listMaintenanceOrders,
  listMaintenancePlans,
  runPreventiveMaintenance,
  scheduleMaintenanceOrder,
  startMaintenanceOrder,
  updateEquipment,
  updateMaintenancePlan,
  type EquipmentFilters,
  type MaintenanceOrderFilters,
  type MaintenancePlanFilters,
} from "@/modules/maintenance/api";
import type {
  CompleteOrderPayload,
  EquipmentCreate,
  EquipmentUpdate,
  MaintenanceOrderCreate,
  MaintenancePlanCreate,
  MaintenancePlanUpdate,
  ScheduleOrderPayload,
} from "@/modules/maintenance/types";

// --- Equipment ----------------------------------------------------------------

export function useEquipmentList(filters: Omit<EquipmentFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["maintenance", "equipment", filters],
    queryFn: ({ pageParam }) =>
      listEquipment({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useEquipment(equipmentId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance", "equipment-item", equipmentId],
    queryFn: () => getEquipment(equipmentId as string),
    enabled: equipmentId !== undefined,
  });
}

/** ACTIVE equipment for the order/plan pickers (a maintenance order targets ACTIVE
 * equipment only) — the useVendorOptions plain-select precedent. */
export function useEquipmentOptions() {
  return useQuery({
    queryKey: ["maintenance", "equipment", "options"],
    queryFn: () => listEquipment({ status: "ACTIVE", limit: 200 }),
    staleTime: 60_000,
  });
}

/** Every unit (no filter) for resolving equipment_id -> code/name on read-only views —
 * an order may reference since-retired equipment. */
export function useEquipmentLookup() {
  return useQuery({
    queryKey: ["maintenance", "equipment", "lookup"],
    queryFn: () => listEquipment({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateEquipment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EquipmentCreate) => createEquipment(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "equipment"] });
    },
  });
}

export function useUpdateEquipment(equipmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EquipmentUpdate) => updateEquipment(equipmentId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "equipment"] });
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "equipment-item", equipmentId] });
    },
  });
}

// --- Maintenance orders -------------------------------------------------------

export function useMaintenanceOrders(filters: Omit<MaintenanceOrderFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["maintenance", "orders", filters],
    queryFn: ({ pageParam }) =>
      listMaintenanceOrders({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMaintenanceOrder(orderId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance", "order", orderId],
    queryFn: () => getMaintenanceOrder(orderId as string),
    enabled: orderId !== undefined,
  });
}

export function useCreateMaintenanceOrder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MaintenanceOrderCreate) => createMaintenanceOrder(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "orders"] });
    },
  });
}

function useOrderAction<TPayload>(
  orderId: string,
  action: (orderId: string, payload: TPayload) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TPayload) => action(orderId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "orders"] });
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "order", orderId] });
    },
  });
}

export function useScheduleMaintenanceOrder(orderId: string) {
  return useOrderAction<ScheduleOrderPayload>(orderId, scheduleMaintenanceOrder);
}

export function useStartMaintenanceOrder(orderId: string) {
  return useOrderAction<void>(orderId, () => startMaintenanceOrder(orderId));
}

export function useCompleteMaintenanceOrder(orderId: string) {
  return useOrderAction<CompleteOrderPayload>(orderId, completeMaintenanceOrder);
}

export function useCancelMaintenanceOrder(orderId: string) {
  return useOrderAction<void>(orderId, () => cancelMaintenanceOrder(orderId));
}

// --- Maintenance plans --------------------------------------------------------

export function useMaintenancePlans(filters: Omit<MaintenancePlanFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["maintenance", "plans", filters],
    queryFn: ({ pageParam }) =>
      listMaintenancePlans({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useMaintenancePlan(planId: string | undefined) {
  return useQuery({
    queryKey: ["maintenance", "plan", planId],
    queryFn: () => getMaintenancePlan(planId as string),
    enabled: planId !== undefined,
  });
}

/** Every plan (no filter) for resolving maintenance_plan_id -> code/name on order views. */
export function useMaintenancePlanLookup() {
  return useQuery({
    queryKey: ["maintenance", "plans", "lookup"],
    queryFn: () => listMaintenancePlans({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useCreateMaintenancePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: MaintenancePlanCreate) => createMaintenancePlan(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "plans"] });
    },
  });
}

function usePlanMutation<TPayload>(
  planId: string,
  action: (payload: TPayload) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "plan", planId] });
    },
  });
}

export function useUpdateMaintenancePlan(planId: string) {
  return usePlanMutation<MaintenancePlanUpdate>(planId, (payload) =>
    updateMaintenancePlan(planId, payload),
  );
}

export function useActivateMaintenancePlan(planId: string) {
  return usePlanMutation<void>(planId, () => activateMaintenancePlan(planId));
}

export function useDeactivateMaintenancePlan(planId: string) {
  return usePlanMutation<void>(planId, () => deactivateMaintenancePlan(planId));
}

export function useRunPreventiveMaintenance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => runPreventiveMaintenance(),
    onSuccess: () => {
      // The run advances due plans AND generates orders — both lists change.
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "plans"] });
      void queryClient.invalidateQueries({ queryKey: ["maintenance", "orders"] });
    },
  });
}
