/**
 * Mirrors backend `app/modules/admin/schemas.py` + `app/modules/industry/schemas.py`
 * (STRUCTURE §4). snake_case kept as-is; UUIDs and timestamps are strings on the wire.
 */

// --- Users / roles / permissions (admin router) --------------------------------

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface UserCreate {
  email: string;
  password: string;
  full_name?: string | null;
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
}

export interface RoleWithPermissions extends Role {
  permissions: string[];
}

export interface RoleCreate {
  name: string;
  permissions: string[];
}

export interface RoleAssign {
  user_id: string;
  role_id: string;
}

export interface Permission {
  key: string;
  description: string | null;
}

// --- Audit viewer --------------------------------------------------------------

export type AuditAction = "INSERT" | "UPDATE" | "DELETE";

/** D-010 diff shapes: UPDATE = {field: {old, new}}; INSERT = {new: fullRow};
 * DELETE = {old: fullRow}. Rendered uniformly by AuditDiffView. */
export interface AuditLog {
  id: string;
  actor_user_id: string | null;
  entity_table: string;
  entity_id: string;
  action: string;
  diff: Record<string, unknown> | null;
  request_id: string | null;
  request_ip: string | null;
  created_at: string;
}

// --- Number sequences (read-only viewer) ----------------------------------------

export interface NumberSequence {
  id: string;
  name: string;
  prefix: string;
  padding: number;
  next_value: number;
  year_reset: boolean;
  current_year: number | null;
}

// --- Onboarding wizard (industry router, PLAN 14.2) -----------------------------

export interface TemplateSummary {
  name: string;
  display_name: string;
  description: string;
  modules: Record<string, boolean>;
}

export interface OnboardTenantRequest {
  company_name: string;
  slug?: string | null;
  template_name: string;
  admin_email: string;
  admin_password: string;
}

export interface OnboardTenantResponse {
  tenant_id: string;
  slug: string;
  admin_user_id: string;
  template_applied: string;
  instantiated: Record<string, number>;
}
