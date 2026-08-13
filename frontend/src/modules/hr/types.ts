/**
 * Mirrors backend `app/modules/hr/schemas.py`, `time_schemas.py`, and `payroll_schemas.py`
 * (STRUCTURE §4): departments + positions + employees + org chart (PLAN 10.1), leave types /
 * balances / requests (10.2), timesheets + time entries + the allocation report (10.3), and
 * payroll runs (10.4). The employee's compensation/PII fields are D-009 MASKED on the wire:
 * they serialize to `null` unless the caller holds `hr.employee.read_compensation`, so every
 * one of them is `string | null` here regardless of what the database holds.
 */

export type EmploymentStatus = "ACTIVE" | "ON_LEAVE" | "TERMINATED";
export type EmploymentType = "FULL_TIME" | "PART_TIME" | "CONTRACT";
export type LeaveRequestStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED" | "CANCELLED";
export type TimesheetStatus = "DRAFT" | "SUBMITTED" | "APPROVED" | "REJECTED";
export type PayrollRunStatus = "DRAFT" | "POSTED" | "CANCELLED";
export type AccrualFrequency = "MONTHLY" | "ANNUAL";
export type LeaveUnit = "DAYS";
export type AllocationDimension = "cost_center" | "project";

// --- Department ---------------------------------------------------------------

export interface Department {
  id: string;
  code: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  cost_center_id: string | null;
  manager_employee_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface DepartmentCreate {
  code: string;
  name: string;
  description?: string | null;
  parent_id?: string | null;
  cost_center_id?: string | null;
  manager_employee_id?: string | null;
  is_active?: boolean;
}

export type DepartmentUpdate = Omit<DepartmentCreate, "code">;

// --- Position -----------------------------------------------------------------

export interface Position {
  id: string;
  code: string;
  title: string;
  description: string | null;
  department_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PositionCreate {
  code: string;
  title: string;
  description?: string | null;
  department_id?: string | null;
  is_active?: boolean;
}

export type PositionUpdate = Omit<PositionCreate, "code">;

// --- Employee -----------------------------------------------------------------

export interface Employee {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  email: string | null;
  department_id: string | null;
  position_id: string | null;
  manager_id: string | null;
  user_id: string | null;
  status: EmploymentStatus;
  employment_type: EmploymentType;
  hire_date: string;
  termination_date: string | null;
  created_at: string;
  updated_at: string;
  // D-009 masked: null unless the caller holds hr.employee.read_compensation.
  base_salary: string | null;
  currency_code: string | null;
  national_id: string | null;
  tax_id: string | null;
  date_of_birth: string | null;
  bank_account: string | null;
}

export interface EmployeeCreate {
  employee_code: string;
  first_name: string;
  last_name: string;
  hire_date: string;
  email?: string | null;
  department_id?: string | null;
  position_id?: string | null;
  manager_id?: string | null;
  user_id?: string | null;
  status?: EmploymentStatus;
  employment_type?: EmploymentType;
  termination_date?: string | null;
  base_salary?: string | null;
  currency_code?: string | null;
  national_id?: string | null;
  tax_id?: string | null;
  date_of_birth?: string | null;
  bank_account?: string | null;
}

/** Non-compensation fields only (the D-009 write-side convention): pay/PII goes through the
 * dedicated compensation endpoint, never the general PATCH. */
export interface EmployeeUpdate {
  first_name?: string;
  last_name?: string;
  email?: string | null;
  department_id?: string | null;
  position_id?: string | null;
  manager_id?: string | null;
  user_id?: string | null;
  status?: EmploymentStatus;
  employment_type?: EmploymentType;
  hire_date?: string;
  termination_date?: string | null;
}

export interface EmployeeCompensationUpdate {
  base_salary?: string | null;
  currency_code?: string | null;
  national_id?: string | null;
  tax_id?: string | null;
  date_of_birth?: string | null;
  bank_account?: string | null;
}

// --- Org chart ----------------------------------------------------------------

export interface OrgChartNode {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  position_id: string | null;
  department_id: string | null;
  reports: OrgChartNode[];
}

export interface OrgChartResponse {
  roots: OrgChartNode[];
}

// --- Leave --------------------------------------------------------------------

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  accrual_frequency: AccrualFrequency;
  accrual_amount: string;
  max_balance: string | null;
  unit: LeaveUnit;
  is_paid: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LeaveTypeCreate {
  code: string;
  name: string;
  accrual_frequency?: AccrualFrequency;
  accrual_amount: string;
  max_balance?: string | null;
  unit?: LeaveUnit;
  is_paid?: boolean;
  is_active?: boolean;
}

export type LeaveTypeUpdate = Omit<LeaveTypeCreate, "code">;

/** Read-only over the API — written by the accrual run and approve/cancel transitions. */
export interface LeaveBalance {
  id: string;
  employee_id: string;
  leave_type_id: string;
  balance_days: string;
  accrued_to_date: string;
  taken_to_date: string;
  last_accrual_period: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccrualResult {
  frequency: AccrualFrequency;
  period: string;
  balances_accrued: number;
}

export interface LeaveRequest {
  id: string;
  request_number: string;
  employee_id: string;
  leave_type_id: string;
  start_date: string;
  end_date: string;
  days: string;
  status: LeaveRequestStatus;
  reason: string | null;
  approved_by: string | null;
  decided_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestCreate {
  employee_id: string;
  leave_type_id: string;
  start_date: string;
  end_date: string;
  days: string;
  reason?: string | null;
  notes?: string | null;
}

export interface LeaveRequestUpdate {
  start_date?: string;
  end_date?: string;
  days?: string;
  reason?: string | null;
  notes?: string | null;
}

export interface LeaveDecision {
  notes?: string | null;
}

// --- Timesheets ---------------------------------------------------------------

export interface Timesheet {
  id: string;
  timesheet_number: string;
  employee_id: string;
  period_start: string;
  period_end: string;
  status: TimesheetStatus;
  total_hours: string;
  submitted_at: string | null;
  approved_at: string | null;
  approved_by: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimesheetCreate {
  employee_id: string;
  period_start: string;
  period_end: string;
  notes?: string | null;
}

export interface TimesheetDecision {
  notes?: string | null;
}

export interface TimeEntry {
  id: string;
  timesheet_id: string;
  entry_date: string;
  hours: string;
  project_id: string | null;
  cost_center_id: string | null;
  task_description: string | null;
  is_billable: boolean;
  created_at: string;
  updated_at: string;
}

export interface TimeEntryCreate {
  entry_date: string;
  hours: string;
  project_id?: string | null;
  cost_center_id?: string | null;
  task_description?: string | null;
  is_billable?: boolean;
}

export interface AllocationRow {
  dimension_id: string | null;
  hours: string;
}

export interface AllocationReport {
  by: AllocationDimension;
  date_from: string;
  date_to: string;
  rows: AllocationRow[];
}

// --- Payroll ------------------------------------------------------------------

export interface PayrollRun {
  id: string;
  run_number: string | null;
  status: PayrollRunStatus;
  period_start: string;
  period_end: string;
  pay_date: string;
  tax_rate_percent: string;
  total_gross: string;
  total_tax: string;
  total_net: string;
  employee_count: number;
  currency_code: string;
  journal_entry_id: string | null;
  posted_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayrollRunCreate {
  period_start: string;
  period_end: string;
  pay_date: string;
  tax_rate_percent?: string | null;
  employee_ids?: string[] | null;
  currency_code?: string | null;
  notes?: string | null;
}

export interface PayrollRunPost {
  notes?: string | null;
}

export interface PayrollRunLine {
  id: string;
  payroll_run_id: string;
  employee_id: string;
  gross_amount: string;
  tax_amount: string;
  net_amount: string;
  cost_center_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayrollRunDetail extends PayrollRun {
  lines: PayrollRunLine[];
}
