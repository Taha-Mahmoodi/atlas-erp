import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activateBom,
  activateRouting,
  createBom,
  createBomComponent,
  createRouting,
  createRoutingOperation,
  createWorkCenter,
  deactivateBom,
  deactivateRouting,
  deleteBomComponent,
  deleteRoutingOperation,
  getBom,
  getRouting,
  getWorkCenter,
  listBomComponents,
  listBoms,
  listRoutingOperations,
  listRoutings,
  listWorkCenters,
  updateBom,
  updateRouting,
  updateWorkCenter,
  type BomFilters,
  type RoutingFilters,
  type WorkCenterFilters,
} from "@/modules/manufacturing/api";
import type {
  BomComponentCreate,
  BomCreate,
  BomUpdate,
  RoutingCreate,
  RoutingOperationCreate,
  RoutingUpdate,
  WorkCenterCreate,
  WorkCenterUpdate,
} from "@/modules/manufacturing/types";

// --- Work centers ---------------------------------------------------------------

export function useWorkCenters(filters: Omit<WorkCenterFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "work-centers", filters],
    queryFn: ({ pageParam }) => listWorkCenters({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All active work centers for a picker (a routing operation's work-center dropdown). */
export function useWorkCenterOptions() {
  return useQuery({
    queryKey: ["manufacturing", "work-centers", "options"],
    queryFn: () => listWorkCenters({ is_active: true, limit: 200 }),
    staleTime: 60_000,
  });
}

export function useWorkCenter(workCenterId: string | undefined) {
  return useQuery({
    queryKey: ["manufacturing", "work-center", workCenterId],
    queryFn: () => getWorkCenter(workCenterId as string),
    enabled: workCenterId !== undefined,
  });
}

function invalidateWorkCenters(queryClient: ReturnType<typeof useQueryClient>, workCenterId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "work-centers"] });
  if (workCenterId) {
    void queryClient.invalidateQueries({ queryKey: ["manufacturing", "work-center", workCenterId] });
  }
}

export function useCreateWorkCenter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkCenterCreate) => createWorkCenter(payload),
    onSuccess: () => invalidateWorkCenters(queryClient),
  });
}

export function useUpdateWorkCenter(workCenterId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkCenterUpdate) => updateWorkCenter(workCenterId, payload),
    onSuccess: () => invalidateWorkCenters(queryClient, workCenterId),
  });
}

// --- BOMs ---------------------------------------------------------------------------

export function useBoms(filters: Omit<BomFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "boms", filters],
    queryFn: ({ pageParam }) => listBoms({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useBom(bomId: string | undefined) {
  return useQuery({
    queryKey: ["manufacturing", "bom", bomId],
    queryFn: () => getBom(bomId as string),
    enabled: bomId !== undefined,
  });
}

function invalidateBom(queryClient: ReturnType<typeof useQueryClient>, bomId: string) {
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "boms"] });
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "bom", bomId] });
}

export function useCreateBom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BomCreate) => createBom(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["manufacturing", "boms"] }),
  });
}

export function useUpdateBom(bomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BomUpdate) => updateBom(bomId, payload),
    onSuccess: () => invalidateBom(queryClient, bomId),
  });
}

export function useActivateBom(bomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateBom(bomId),
    onSuccess: () => invalidateBom(queryClient, bomId),
  });
}

export function useDeactivateBom(bomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deactivateBom(bomId),
    onSuccess: () => invalidateBom(queryClient, bomId),
  });
}

export function useBomComponents(bomId: string) {
  return useQuery({
    queryKey: ["manufacturing", "bom-components", bomId],
    queryFn: () => listBomComponents(bomId),
  });
}

export function useCreateBomComponent(bomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BomComponentCreate) => createBomComponent(bomId, payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["manufacturing", "bom-components", bomId] }),
  });
}

export function useDeleteBomComponent(bomId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (componentId: string) => deleteBomComponent(bomId, componentId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["manufacturing", "bom-components", bomId] }),
  });
}

// --- Routings -------------------------------------------------------------------------

export function useRoutings(filters: Omit<RoutingFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["manufacturing", "routings", filters],
    queryFn: ({ pageParam }) => listRoutings({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useRouting(routingId: string | undefined) {
  return useQuery({
    queryKey: ["manufacturing", "routing", routingId],
    queryFn: () => getRouting(routingId as string),
    enabled: routingId !== undefined,
  });
}

function invalidateRouting(queryClient: ReturnType<typeof useQueryClient>, routingId: string) {
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "routings"] });
  void queryClient.invalidateQueries({ queryKey: ["manufacturing", "routing", routingId] });
}

export function useCreateRouting() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoutingCreate) => createRouting(payload),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["manufacturing", "routings"] }),
  });
}

export function useUpdateRouting(routingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoutingUpdate) => updateRouting(routingId, payload),
    onSuccess: () => invalidateRouting(queryClient, routingId),
  });
}

export function useActivateRouting(routingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => activateRouting(routingId),
    onSuccess: () => invalidateRouting(queryClient, routingId),
  });
}

export function useDeactivateRouting(routingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deactivateRouting(routingId),
    onSuccess: () => invalidateRouting(queryClient, routingId),
  });
}

export function useRoutingOperations(routingId: string) {
  return useQuery({
    queryKey: ["manufacturing", "routing-operations", routingId],
    queryFn: () => listRoutingOperations(routingId),
  });
}

export function useCreateRoutingOperation(routingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoutingOperationCreate) => createRoutingOperation(routingId, payload),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["manufacturing", "routing-operations", routingId] }),
  });
}

export function useDeleteRoutingOperation(routingId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (operationId: string) => deleteRoutingOperation(routingId, operationId),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["manufacturing", "routing-operations", routingId] }),
  });
}
