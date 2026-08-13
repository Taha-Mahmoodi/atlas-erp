/**
 * Typed endpoint calls for the CRM module (STRUCTURE §4): leads (+ qualify/disqualify/convert),
 * opportunities (+ kanban board, move-stage, convert-to-customer+quote), activities
 * (+ complete/cancel). CRM rows are pipeline masters, not financial documents — no idempotency
 * keys (D-013 applies to document-creating endpoints only; these routers carry none).
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  Activity,
  ActivityCreate,
  ActivityStatus,
  ConvertLead,
  KanbanBoardData,
  Lead,
  LeadCreate,
  LeadStatus,
  LeadUpdate,
  Opportunity,
  OpportunityCreate,
  OpportunityDetail,
  OpportunityStage,
  OpportunityUpdate,
} from "@/modules/crm/types";

// --- Leads --------------------------------------------------------------------

export interface LeadFilters {
  cursor?: string;
  limit?: number;
  status?: LeadStatus;
}

export function listLeads(filters: LeadFilters = {}): Promise<Page<Lead>> {
  return api.get<Page<Lead>>("/crm/leads", { params: { ...filters } });
}

export function getLead(leadId: string): Promise<Lead> {
  return api.get<Lead>(`/crm/leads/${leadId}`);
}

export function createLead(payload: LeadCreate): Promise<Lead> {
  return api.post<Lead>("/crm/leads", payload);
}

export function updateLead(leadId: string, payload: LeadUpdate): Promise<Lead> {
  return api.patch<Lead>(`/crm/leads/${leadId}`, payload);
}

export function qualifyLead(leadId: string): Promise<Lead> {
  return api.post<Lead>(`/crm/leads/${leadId}/qualify`);
}

export function disqualifyLead(leadId: string): Promise<Lead> {
  return api.post<Lead>(`/crm/leads/${leadId}/disqualify`);
}

/** QUALIFIED lead → DRAFT opportunity; returns the new opportunity header. */
export function convertLead(leadId: string, payload: ConvertLead): Promise<Opportunity> {
  return api.post<Opportunity>(`/crm/leads/${leadId}/convert`, payload);
}

// --- Opportunities ------------------------------------------------------------

export function getKanbanBoard(): Promise<KanbanBoardData> {
  return api.get<KanbanBoardData>("/crm/opportunities/kanban");
}

export function getOpportunity(opportunityId: string): Promise<OpportunityDetail> {
  return api.get<OpportunityDetail>(`/crm/opportunities/${opportunityId}`);
}

export function createOpportunity(payload: OpportunityCreate): Promise<OpportunityDetail> {
  return api.post<OpportunityDetail>("/crm/opportunities", payload);
}

export function updateOpportunity(
  opportunityId: string,
  payload: OpportunityUpdate,
): Promise<OpportunityDetail> {
  return api.patch<OpportunityDetail>(`/crm/opportunities/${opportunityId}`, payload);
}

/** The kanban move (D-057): any open stage → any open stage or WON/LOST; terminal stages are fixed. */
export function moveOpportunityStage(
  opportunityId: string,
  stage: OpportunityStage,
): Promise<OpportunityDetail> {
  return api.post<OpportunityDetail>(`/crm/opportunities/${opportunityId}/move-stage`, { stage });
}

/** Convert → sales customer (if new) + quote; the response carries the converted ids. The body
 * is parameterless in v1 (D-057), reserved for later overrides. */
export function convertOpportunity(opportunityId: string): Promise<OpportunityDetail> {
  return api.post<OpportunityDetail>(`/crm/opportunities/${opportunityId}/convert`, {});
}

// --- Activities ---------------------------------------------------------------

export interface ActivityFilters {
  cursor?: string;
  limit?: number;
  status?: ActivityStatus;
  lead_id?: string;
  opportunity_id?: string;
}

export function listActivities(filters: ActivityFilters = {}): Promise<Page<Activity>> {
  return api.get<Page<Activity>>("/crm/activities", { params: { ...filters } });
}

export function createActivity(payload: ActivityCreate): Promise<Activity> {
  return api.post<Activity>("/crm/activities", payload);
}

export function completeActivity(activityId: string): Promise<Activity> {
  // completed_date defaults to today server-side.
  return api.post<Activity>(`/crm/activities/${activityId}/complete`, {});
}

export function cancelActivity(activityId: string): Promise<Activity> {
  return api.post<Activity>(`/crm/activities/${activityId}/cancel`);
}
