/**
 * Typed endpoint calls for the admin module (STRUCTURE §4): user/role management, the
 * audit viewer, number sequences (all `/admin`), plus the tenant-onboarding wizard's
 * template catalog (`/industry`) and provisioning call (`/onboarding`) — PLAN 15.12.
 * Exchange rates and tax codes are NOT here: they are finance's API (finance/api.ts);
 * the admin home page only cross-links their pages, mirroring the backend's split.
 */

import { api, type Page } from "@/lib/apiClient";
import type {
  AuditLog,
  NumberSequence,
  OnboardTenantRequest,
  OnboardTenantResponse,
  Permission,
  Role,
  RoleAssign,
  RoleCreate,
  RoleWithPermissions,
  TemplateSummary,
  User,
  UserCreate,
} from "@/modules/admin/types";

// --- Users --------------------------------------------------------------------

export interface UserFilters {
  cursor?: string;
  limit?: number;
}

export function listUsers(filters: UserFilters = {}): Promise<Page<User>> {
  return api.get<Page<User>>("/admin/users", { params: { ...filters } });
}

export function getUser(userId: string): Promise<User> {
  return api.get<User>(`/admin/users/${userId}`);
}

export function createUser(payload: UserCreate): Promise<User> {
  return api.post<User>("/admin/users", payload);
}

export function listUserRoles(userId: string): Promise<Role[]> {
  return api.get<Role[]>(`/admin/users/${userId}/roles`);
}

export function assignRole(payload: RoleAssign): Promise<{ status: string }> {
  return api.post<{ status: string }>("/admin/users/assign-role", payload);
}

// --- Roles + permission catalog -----------------------------------------------

export function listRoles(filters: UserFilters = {}): Promise<Page<Role>> {
  return api.get<Page<Role>>("/admin/roles", { params: { ...filters } });
}

export function getRole(roleId: string): Promise<RoleWithPermissions> {
  return api.get<RoleWithPermissions>(`/admin/roles/${roleId}`);
}

export function createRole(payload: RoleCreate): Promise<RoleWithPermissions> {
  return api.post<RoleWithPermissions>("/admin/roles", payload);
}

export function listPermissions(): Promise<Permission[]> {
  return api.get<Permission[]>("/admin/permissions");
}

// --- Audit viewer --------------------------------------------------------------

export interface AuditLogFilters {
  cursor?: string;
  limit?: number;
  entity_table?: string;
  entity_id?: string;
  actor_user_id?: string;
  action?: string;
  created_from?: string;
  created_to?: string;
}

export function listAuditLogs(filters: AuditLogFilters = {}): Promise<Page<AuditLog>> {
  return api.get<Page<AuditLog>>("/admin/audit-logs", { params: { ...filters } });
}

// --- Number sequences -----------------------------------------------------------

export function listNumberSequences(filters: UserFilters = {}): Promise<Page<NumberSequence>> {
  return api.get<Page<NumberSequence>>("/admin/number-sequences", { params: { ...filters } });
}

// --- Onboarding wizard -----------------------------------------------------------

export function listIndustryTemplates(): Promise<TemplateSummary[]> {
  return api.get<TemplateSummary[]>("/industry/templates");
}

export function onboardTenant(payload: OnboardTenantRequest): Promise<OnboardTenantResponse> {
  return api.post<OnboardTenantResponse>("/onboarding/tenants", payload);
}
