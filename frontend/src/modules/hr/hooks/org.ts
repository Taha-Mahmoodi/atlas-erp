/**
 * TanStack Query hooks for the HR org core (PLAN 10.1): departments, positions, employees
 * (masked compensation), the dedicated compensation write, and the org chart. Split by
 * sub-area from day one (the sales/procurement hooks/ precedent) since the module ships in
 * one PR.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createDepartment,
  createEmployee,
  createPosition,
  type DepartmentFilters,
  type EmployeeFilters,
  getDepartment,
  getEmployee,
  getOrgChart,
  getPosition,
  listCostCenters,
  listDepartments,
  listEmployees,
  listPositions,
  type PositionFilters,
  setEmployeeCompensation,
  updateDepartment,
  updateEmployee,
  updatePosition,
} from "@/modules/hr/api";
import type {
  DepartmentCreate,
  DepartmentUpdate,
  EmployeeCompensationUpdate,
  EmployeeCreate,
  EmployeeUpdate,
  PositionCreate,
  PositionUpdate,
} from "@/modules/hr/types";

// --- Departments ---------------------------------------------------------------

export function useDepartments(filters: Omit<DepartmentFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "departments", filters],
    queryFn: ({ pageParam }) => listDepartments({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All departments for a picker (parent / employee's department dropdowns + label lookups). */
export function useDepartmentOptions() {
  return useQuery({
    queryKey: ["hr", "departments", "options"],
    queryFn: () => listDepartments({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useDepartment(departmentId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "department", departmentId],
    queryFn: () => getDepartment(departmentId as string),
    enabled: departmentId !== undefined,
  });
}

function invalidateDepartments(queryClient: ReturnType<typeof useQueryClient>, departmentId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "departments"] });
  if (departmentId) void queryClient.invalidateQueries({ queryKey: ["hr", "department", departmentId] });
}

export function useCreateDepartment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DepartmentCreate) => createDepartment(payload),
    onSuccess: () => invalidateDepartments(queryClient),
  });
}

export function useUpdateDepartment(departmentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: DepartmentUpdate) => updateDepartment(departmentId, payload),
    onSuccess: () => invalidateDepartments(queryClient, departmentId),
  });
}

// --- Positions -----------------------------------------------------------------

export function usePositions(filters: Omit<PositionFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "positions", filters],
    queryFn: ({ pageParam }) => listPositions({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All positions for a picker (employee's position dropdown + org-chart title lookups). */
export function usePositionOptions() {
  return useQuery({
    queryKey: ["hr", "positions", "options"],
    queryFn: () => listPositions({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function usePosition(positionId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "position", positionId],
    queryFn: () => getPosition(positionId as string),
    enabled: positionId !== undefined,
  });
}

function invalidatePositions(queryClient: ReturnType<typeof useQueryClient>, positionId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "positions"] });
  if (positionId) void queryClient.invalidateQueries({ queryKey: ["hr", "position", positionId] });
}

export function useCreatePosition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PositionCreate) => createPosition(payload),
    onSuccess: () => invalidatePositions(queryClient),
  });
}

export function useUpdatePosition(positionId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PositionUpdate) => updatePosition(positionId, payload),
    onSuccess: () => invalidatePositions(queryClient, positionId),
  });
}

// --- Employees -----------------------------------------------------------------

export function useEmployees(filters: Omit<EmployeeFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["hr", "employees", filters],
    queryFn: ({ pageParam }) => listEmployees({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** All employees for a picker (manager / leave / timesheet dropdowns + label lookups). */
export function useEmployeeOptions() {
  return useQuery({
    queryKey: ["hr", "employees", "options"],
    queryFn: () => listEmployees({ limit: 200 }),
    staleTime: 60_000,
  });
}

export function useEmployee(employeeId: string | undefined) {
  return useQuery({
    queryKey: ["hr", "employee", employeeId],
    queryFn: () => getEmployee(employeeId as string),
    enabled: employeeId !== undefined,
  });
}

function invalidateEmployees(queryClient: ReturnType<typeof useQueryClient>, employeeId?: string) {
  void queryClient.invalidateQueries({ queryKey: ["hr", "employees"] });
  if (employeeId) void queryClient.invalidateQueries({ queryKey: ["hr", "employee", employeeId] });
  void queryClient.invalidateQueries({ queryKey: ["hr", "org-chart"] });
}

export function useCreateEmployee() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmployeeCreate) => createEmployee(payload),
    onSuccess: () => invalidateEmployees(queryClient),
  });
}

export function useUpdateEmployee(employeeId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmployeeUpdate) => updateEmployee(employeeId, payload),
    onSuccess: () => invalidateEmployees(queryClient, employeeId),
  });
}

export function useSetEmployeeCompensation(employeeId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmployeeCompensationUpdate) => setEmployeeCompensation(employeeId, payload),
    onSuccess: () => invalidateEmployees(queryClient, employeeId),
  });
}

// --- Org chart -----------------------------------------------------------------

export function useOrgChart(rootEmployeeId?: string) {
  return useQuery({
    queryKey: ["hr", "org-chart", rootEmployeeId ?? null],
    queryFn: () => getOrgChart(rootEmployeeId),
  });
}

// --- Cost centers (finance-owned; department + time-entry pickers) ---------------

export function useCostCenterOptions() {
  return useQuery({
    queryKey: ["hr", "cost-centers", "options"],
    queryFn: () => listCostCenters(),
    staleTime: 60_000,
  });
}
