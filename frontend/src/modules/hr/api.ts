/**
 * Typed endpoint calls for the hr module (STRUCTURE §4): departments, positions, employees +
 * the masked-compensation write path + the org chart (PLAN 10.1), leave types / balances /
 * the accrual run / leave requests (10.2), timesheets + nested time entries + the allocation
 * report (10.3), and payroll runs (10.4). Idempotency keys (D-013) mirror the backend's
 * actual `Idempotent(...)` deps exactly: leave-request create/submit/approve/reject, the
 * accrual run, timesheet create/submit/approve/reject, and payroll create/post carry one;
 * master-data CRUD, cancels, PATCHes, and time-entry writes do not.
 */

import { api, newIdempotencyKey, type Page } from "@/lib/apiClient";
import type {
  AccrualFrequency,
  AccrualResult,
  AllocationDimension,
  AllocationReport,
  Department,
  DepartmentCreate,
  DepartmentUpdate,
  Employee,
  EmployeeCompensationUpdate,
  EmployeeCreate,
  EmployeeUpdate,
  EmploymentStatus,
  LeaveBalance,
  LeaveDecision,
  LeaveRequest,
  LeaveRequestCreate,
  LeaveRequestStatus,
  LeaveRequestUpdate,
  LeaveType,
  LeaveTypeCreate,
  LeaveTypeUpdate,
  OrgChartResponse,
  PayrollRun,
  PayrollRunCreate,
  PayrollRunDetail,
  PayrollRunLine,
  PayrollRunPost,
  PayrollRunStatus,
  Position,
  PositionCreate,
  PositionUpdate,
  TimeEntry,
  TimeEntryCreate,
  Timesheet,
  TimesheetCreate,
  TimesheetDecision,
  TimesheetStatus,
} from "@/modules/hr/types";

// --- Departments ---------------------------------------------------------------

export interface DepartmentFilters {
  cursor?: string;
  limit?: number;
  is_active?: boolean;
  parent_id?: string;
}

export function listDepartments(filters: DepartmentFilters = {}): Promise<Page<Department>> {
  return api.get<Page<Department>>("/hr/departments", { params: { ...filters } });
}

export function getDepartment(departmentId: string): Promise<Department> {
  return api.get<Department>(`/hr/departments/${departmentId}`);
}

export function createDepartment(payload: DepartmentCreate): Promise<Department> {
  return api.post<Department>("/hr/departments", payload);
}

export function updateDepartment(departmentId: string, payload: DepartmentUpdate): Promise<Department> {
  return api.patch<Department>(`/hr/departments/${departmentId}`, payload);
}

// --- Positions -----------------------------------------------------------------

export interface PositionFilters {
  cursor?: string;
  limit?: number;
  is_active?: boolean;
  department_id?: string;
}

export function listPositions(filters: PositionFilters = {}): Promise<Page<Position>> {
  return api.get<Page<Position>>("/hr/positions", { params: { ...filters } });
}

export function getPosition(positionId: string): Promise<Position> {
  return api.get<Position>(`/hr/positions/${positionId}`);
}

export function createPosition(payload: PositionCreate): Promise<Position> {
  return api.post<Position>("/hr/positions", payload);
}

export function updatePosition(positionId: string, payload: PositionUpdate): Promise<Position> {
  return api.patch<Position>(`/hr/positions/${positionId}`, payload);
}

// --- Employees -----------------------------------------------------------------

export interface EmployeeFilters {
  cursor?: string;
  limit?: number;
  department_id?: string;
  status?: EmploymentStatus;
  manager_id?: string;
}

export function listEmployees(filters: EmployeeFilters = {}): Promise<Page<Employee>> {
  return api.get<Page<Employee>>("/hr/employees", { params: { ...filters } });
}

export function getEmployee(employeeId: string): Promise<Employee> {
  return api.get<Employee>(`/hr/employees/${employeeId}`);
}

export function createEmployee(payload: EmployeeCreate): Promise<Employee> {
  return api.post<Employee>("/hr/employees", payload);
}

export function updateEmployee(employeeId: string, payload: EmployeeUpdate): Promise<Employee> {
  return api.patch<Employee>(`/hr/employees/${employeeId}`, payload);
}

export function setEmployeeCompensation(
  employeeId: string,
  payload: EmployeeCompensationUpdate,
): Promise<Employee> {
  return api.patch<Employee>(`/hr/employees/${employeeId}/compensation`, payload);
}

export function getOrgChart(rootEmployeeId?: string): Promise<OrgChartResponse> {
  return api.get<OrgChartResponse>("/hr/employees/org-chart", {
    params: rootEmployeeId ? { root_employee_id: rootEmployeeId } : {},
  });
}

// --- Leave types ---------------------------------------------------------------

export interface LeaveTypeFilters {
  cursor?: string;
  limit?: number;
  is_active?: boolean;
  accrual_frequency?: AccrualFrequency;
}

export function listLeaveTypes(filters: LeaveTypeFilters = {}): Promise<Page<LeaveType>> {
  return api.get<Page<LeaveType>>("/hr/leave-types", { params: { ...filters } });
}

export function getLeaveType(leaveTypeId: string): Promise<LeaveType> {
  return api.get<LeaveType>(`/hr/leave-types/${leaveTypeId}`);
}

export function createLeaveType(payload: LeaveTypeCreate): Promise<LeaveType> {
  return api.post<LeaveType>("/hr/leave-types", payload);
}

export function updateLeaveType(leaveTypeId: string, payload: LeaveTypeUpdate): Promise<LeaveType> {
  return api.patch<LeaveType>(`/hr/leave-types/${leaveTypeId}`, payload);
}

// --- Leave balances + the accrual run -------------------------------------------

export function listEmployeeLeaveBalances(employeeId: string): Promise<LeaveBalance[]> {
  return api.get<LeaveBalance[]>(`/hr/employees/${employeeId}/leave-balances`);
}

export function runLeaveAccrual(frequency: AccrualFrequency, asOf?: string): Promise<AccrualResult> {
  return api.post<AccrualResult>("/hr/leave-balances/accrue", undefined, {
    params: { frequency, ...(asOf ? { as_of: asOf } : {}) },
    idempotencyKey: newIdempotencyKey(),
  });
}

// --- Leave requests ------------------------------------------------------------

export interface LeaveRequestFilters {
  cursor?: string;
  limit?: number;
  employee_id?: string;
  status?: LeaveRequestStatus;
  leave_type_id?: string;
}

export function listLeaveRequests(filters: LeaveRequestFilters = {}): Promise<Page<LeaveRequest>> {
  return api.get<Page<LeaveRequest>>("/hr/leave-requests", { params: { ...filters } });
}

export function getLeaveRequest(requestId: string): Promise<LeaveRequest> {
  return api.get<LeaveRequest>(`/hr/leave-requests/${requestId}`);
}

export function createLeaveRequest(payload: LeaveRequestCreate): Promise<LeaveRequest> {
  return api.post<LeaveRequest>("/hr/leave-requests", payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function updateLeaveRequest(requestId: string, payload: LeaveRequestUpdate): Promise<LeaveRequest> {
  return api.patch<LeaveRequest>(`/hr/leave-requests/${requestId}`, payload);
}

export function submitLeaveRequest(requestId: string): Promise<LeaveRequest> {
  return api.post<LeaveRequest>(`/hr/leave-requests/${requestId}/submit`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function approveLeaveRequest(requestId: string, payload: LeaveDecision): Promise<LeaveRequest> {
  return api.post<LeaveRequest>(`/hr/leave-requests/${requestId}/approve`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function rejectLeaveRequest(requestId: string, payload: LeaveDecision): Promise<LeaveRequest> {
  return api.post<LeaveRequest>(`/hr/leave-requests/${requestId}/reject`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelLeaveRequest(requestId: string): Promise<LeaveRequest> {
  return api.post<LeaveRequest>(`/hr/leave-requests/${requestId}/cancel`, undefined);
}

// --- Timesheets ----------------------------------------------------------------

export interface TimesheetFilters {
  cursor?: string;
  limit?: number;
  employee_id?: string;
  status?: TimesheetStatus;
  period_from?: string;
  period_to?: string;
}

export function listTimesheets(filters: TimesheetFilters = {}): Promise<Page<Timesheet>> {
  return api.get<Page<Timesheet>>("/hr/timesheets", { params: { ...filters } });
}

export function getTimesheet(timesheetId: string): Promise<Timesheet> {
  return api.get<Timesheet>(`/hr/timesheets/${timesheetId}`);
}

export function createTimesheet(payload: TimesheetCreate): Promise<Timesheet> {
  return api.post<Timesheet>("/hr/timesheets", payload, { idempotencyKey: newIdempotencyKey() });
}

export function submitTimesheet(timesheetId: string): Promise<Timesheet> {
  return api.post<Timesheet>(`/hr/timesheets/${timesheetId}/submit`, undefined, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function approveTimesheet(timesheetId: string, payload: TimesheetDecision): Promise<Timesheet> {
  return api.post<Timesheet>(`/hr/timesheets/${timesheetId}/approve`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function rejectTimesheet(timesheetId: string, payload: TimesheetDecision): Promise<Timesheet> {
  return api.post<Timesheet>(`/hr/timesheets/${timesheetId}/reject`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

/** Reopens a SUBMITTED timesheet to DRAFT (the backend's "cancel" verb) for edit + resubmit. */
export function cancelTimesheet(timesheetId: string): Promise<Timesheet> {
  return api.post<Timesheet>(`/hr/timesheets/${timesheetId}/cancel`, undefined);
}

// --- Time entries --------------------------------------------------------------

export function listTimeEntries(timesheetId: string): Promise<TimeEntry[]> {
  return api.get<TimeEntry[]>(`/hr/timesheets/${timesheetId}/time-entries`);
}

export function addTimeEntry(timesheetId: string, payload: TimeEntryCreate): Promise<TimeEntry> {
  return api.post<TimeEntry>(`/hr/timesheets/${timesheetId}/time-entries`, payload);
}

export function removeTimeEntry(timesheetId: string, entryId: string): Promise<void> {
  return api.delete<void>(`/hr/timesheets/${timesheetId}/time-entries/${entryId}`);
}

export function getTimeAllocation(
  by: AllocationDimension,
  dateFrom: string,
  dateTo: string,
): Promise<AllocationReport> {
  return api.get<AllocationReport>("/hr/timesheets/allocation", {
    params: { by, from: dateFrom, to: dateTo },
  });
}

// --- Payroll runs --------------------------------------------------------------

export interface PayrollRunFilters {
  cursor?: string;
  limit?: number;
  status?: PayrollRunStatus;
  period_from?: string;
  period_to?: string;
}

export function listPayrollRuns(filters: PayrollRunFilters = {}): Promise<Page<PayrollRun>> {
  return api.get<Page<PayrollRun>>("/hr/payroll-runs", { params: { ...filters } });
}

export function getPayrollRun(runId: string): Promise<PayrollRunDetail> {
  return api.get<PayrollRunDetail>(`/hr/payroll-runs/${runId}`);
}

export function listPayrollRunLines(runId: string): Promise<PayrollRunLine[]> {
  return api.get<PayrollRunLine[]>(`/hr/payroll-runs/${runId}/lines`);
}

export function createPayrollRun(payload: PayrollRunCreate): Promise<PayrollRun> {
  return api.post<PayrollRun>("/hr/payroll-runs", payload, { idempotencyKey: newIdempotencyKey() });
}

export function postPayrollRun(runId: string, payload: PayrollRunPost): Promise<PayrollRun> {
  return api.post<PayrollRun>(`/hr/payroll-runs/${runId}/post`, payload, {
    idempotencyKey: newIdempotencyKey(),
  });
}

export function cancelPayrollRun(runId: string): Promise<PayrollRun> {
  return api.post<PayrollRun>(`/hr/payroll-runs/${runId}/cancel`, undefined);
}

// --- Cost centers (finance-owned reference data) --------------------------------
// The finance frontend has no cost-center hook to import (its journal pages never needed a
// picker), so HR reads the read-only list endpoint directly for department / time-entry pickers.

export interface CostCenterOption {
  id: string;
  code: string;
  name: string;
}

export function listCostCenters(limit = 200): Promise<Page<CostCenterOption>> {
  return api.get<Page<CostCenterOption>>("/finance/cost-centers", { params: { limit } });
}
