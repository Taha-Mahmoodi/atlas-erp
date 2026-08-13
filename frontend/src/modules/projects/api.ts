/**
 * Typed endpoint calls for the projects module (STRUCTURE §4): projects, WBS elements
 * (nested under a project), and the project cost report. Projects/WBS are MASTERS, not
 * documents — no idempotency keys anywhere (D-013 applies to document-creating endpoints
 * only; the backend's projects routers carry no IdempotentDep).
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  Project,
  ProjectCostReport,
  ProjectCreate,
  ProjectStatus,
  ProjectUpdate,
  WbsElement,
  WbsElementCreate,
  WbsElementUpdate,
  WbsStatus,
} from "@/modules/projects/types";

export interface ProjectFilters {
  cursor?: string;
  limit?: number;
  status?: ProjectStatus;
}

export function listProjects(filters: ProjectFilters = {}): Promise<Page<Project>> {
  return api.get<Page<Project>>("/projects", { params: { ...filters } });
}

export function getProject(projectId: string): Promise<Project> {
  return api.get<Project>(`/projects/${projectId}`);
}

export function createProject(payload: ProjectCreate): Promise<Project> {
  return api.post<Project>("/projects", payload);
}

export function updateProject(projectId: string, payload: ProjectUpdate): Promise<Project> {
  return api.patch<Project>(`/projects/${projectId}`, payload);
}

export function getProjectCostReport(projectId: string, asOf?: string): Promise<ProjectCostReport> {
  return api.get<ProjectCostReport>(`/projects/${projectId}/cost-report`, {
    params: { as_of: asOf },
  });
}

// --- WBS elements ----------------------------------------------------------------

export interface WbsElementFilters {
  cursor?: string;
  limit?: number;
  status?: WbsStatus;
}

export function listWbsElements(
  projectId: string,
  filters: WbsElementFilters = {},
): Promise<Page<WbsElement>> {
  return api.get<Page<WbsElement>>(`/projects/${projectId}/wbs-elements`, {
    params: { ...filters },
  });
}

export function getWbsElement(wbsElementId: string): Promise<WbsElement> {
  return api.get<WbsElement>(`/projects/wbs-elements/${wbsElementId}`);
}

export function createWbsElement(
  projectId: string,
  payload: WbsElementCreate,
): Promise<WbsElement> {
  return api.post<WbsElement>(`/projects/${projectId}/wbs-elements`, payload);
}

export function updateWbsElement(
  wbsElementId: string,
  payload: WbsElementUpdate,
): Promise<WbsElement> {
  return api.patch<WbsElement>(`/projects/wbs-elements/${wbsElementId}`, payload);
}
