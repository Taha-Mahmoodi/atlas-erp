/**
 * Mirrors backend `app/modules/projects/schemas.py` (STRUCTURE §4): the two masters
 * (Project, WbsElement) and the project cost report (D-056). Money is Decimal-as-string
 * (D-015), snake_case untranslated.
 */

export type ProjectStatus = "PLANNING" | "ACTIVE" | "CLOSED" | "CANCELLED";
export type WbsStatus = "OPEN" | "CLOSED";

export interface Project {
  id: string;
  code: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  customer_id: string | null;
  cost_center_id: string | null;
  start_date: string | null;
  end_date: string | null;
  budget_amount: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  code: string;
  name: string;
  description?: string | null;
  status?: ProjectStatus;
  customer_id?: string | null;
  cost_center_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  budget_amount?: string | null;
  is_active?: boolean;
}

/** `code` is immutable after creation (the work-centre precedent). */
export type ProjectUpdate = Omit<ProjectCreate, "code">;

export interface WbsElement {
  id: string;
  project_id: string;
  code: string;
  name: string;
  parent_id: string | null;
  status: WbsStatus;
  is_billable: boolean;
  budget_amount: string | null;
  created_at: string;
  updated_at: string;
}

export interface WbsElementCreate {
  code: string;
  name: string;
  parent_id?: string | null;
  status?: WbsStatus;
  is_billable?: boolean;
  budget_amount?: string | null;
}

export type WbsElementUpdate = Omit<WbsElementCreate, "code">;

// --- Project cost report (D-056) ----------------------------------------------

export interface WbsCostLine {
  wbs_element_id: string;
  code: string;
  name: string;
  status: WbsStatus;
  parent_id: string | null;
  budget_amount: string;
  actual_cost: string;
  hours: string;
  variance: string;
}

export interface ProjectCostReport {
  project_id: string;
  project_code: string;
  project_name: string;
  project_status: ProjectStatus;
  as_of_date: string | null;
  total_budget: string;
  total_actual_cost: string;
  total_hours: string;
  total_variance: string;
  lines: WbsCostLine[];
}
