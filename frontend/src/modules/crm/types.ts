/**
 * Mirrors backend `app/modules/crm/schemas.py` (STRUCTURE §4): leads, opportunities (+lines),
 * activities, the kanban board (D-057) and the action payloads. Money is Decimal-as-string
 * (D-015), snake_case untranslated.
 */

export type LeadStatus = "NEW" | "CONTACTED" | "QUALIFIED" | "DISQUALIFIED" | "CONVERTED";
export type OpportunityStage =
  | "PROSPECTING"
  | "QUALIFICATION"
  | "PROPOSAL"
  | "NEGOTIATION"
  | "WON"
  | "LOST";
export type ActivityType = "CALL" | "EMAIL" | "MEETING" | "TASK" | "NOTE";
export type ActivityStatus = "OPEN" | "COMPLETED" | "CANCELLED";

/** The kanban columns in the backend's declared order (open stages then terminal). */
export const OPEN_STAGES: OpportunityStage[] = [
  "PROSPECTING",
  "QUALIFICATION",
  "PROPOSAL",
  "NEGOTIATION",
];
export const TERMINAL_STAGES: OpportunityStage[] = ["WON", "LOST"];

// --- Leads --------------------------------------------------------------------

export interface Lead {
  id: string;
  lead_number: string;
  status: LeadStatus;
  company_name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  source: string | null;
  estimated_value: string | null;
  currency_code: string | null;
  owner_employee_id: string | null;
  notes: string | null;
  converted_opportunity_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeadCreate {
  company_name: string;
  contact_name?: string | null;
  email?: string | null;
  phone?: string | null;
  source?: string | null;
  status?: LeadStatus;
  estimated_value?: string | null;
  currency_code?: string | null;
  owner_employee_id?: string | null;
  notes?: string | null;
}

/** `status` moves via the qualify/disqualify actions, never a free edit. */
export type LeadUpdate = Omit<LeadCreate, "status">;

export interface ConvertLead {
  name?: string | null;
  expected_close_date?: string | null;
  probability_percent?: string | null;
  notes?: string | null;
}

// --- Opportunities ------------------------------------------------------------

export interface OpportunityLineCreate {
  item_id: string;
  description?: string | null;
  quantity: string;
  estimated_unit_price: string;
}

export interface OpportunityLine {
  id: string;
  line_number: number;
  item_id: string;
  description: string | null;
  quantity: string;
  estimated_unit_price: string;
}

/** Header without lines — the list-row / kanban-card shape (`OpportunityRead`). */
export interface Opportunity {
  id: string;
  opportunity_number: string;
  name: string;
  stage: OpportunityStage;
  source_lead_id: string | null;
  customer_id: string | null;
  company_name: string;
  contact_name: string | null;
  email: string | null;
  estimated_value: string;
  currency_code: string;
  probability_percent: string | null;
  expected_close_date: string | null;
  owner_employee_id: string | null;
  notes: string | null;
  converted_customer_id: string | null;
  converted_quote_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface OpportunityDetail extends Opportunity {
  lines: OpportunityLine[];
}

export interface OpportunityCreate {
  name: string;
  company_name: string;
  contact_name?: string | null;
  email?: string | null;
  customer_id?: string | null;
  currency_code: string;
  estimated_value?: string;
  probability_percent?: string | null;
  expected_close_date?: string | null;
  owner_employee_id?: string | null;
  notes?: string | null;
  lines?: OpportunityLineCreate[];
}

/** `stage` moves via the move-stage action; lines (when supplied) replace wholesale. */
export interface OpportunityUpdate {
  name?: string | null;
  company_name?: string | null;
  contact_name?: string | null;
  email?: string | null;
  customer_id?: string | null;
  currency_code?: string | null;
  estimated_value?: string | null;
  probability_percent?: string | null;
  expected_close_date?: string | null;
  owner_employee_id?: string | null;
  notes?: string | null;
  lines?: OpportunityLineCreate[] | null;
}

// --- Kanban board (D-057) -----------------------------------------------------

export interface KanbanBoardColumn {
  stage: OpportunityStage;
  count: number;
  total_estimated_value: string;
  opportunities: Opportunity[];
}

export interface KanbanBoardData {
  column_limit: number;
  columns: KanbanBoardColumn[];
}

// --- Activities ---------------------------------------------------------------

export interface Activity {
  id: string;
  activity_type: ActivityType;
  status: ActivityStatus;
  subject: string;
  description: string | null;
  due_date: string | null;
  completed_date: string | null;
  lead_id: string | null;
  opportunity_id: string | null;
  owner_employee_id: string | null;
  created_at: string;
  updated_at: string;
}

/** Exactly one of `lead_id` / `opportunity_id` — the parent is immutable after creation. */
export interface ActivityCreate {
  activity_type: ActivityType;
  subject: string;
  description?: string | null;
  status?: ActivityStatus;
  due_date?: string | null;
  lead_id?: string | null;
  opportunity_id?: string | null;
  owner_employee_id?: string | null;
}
