/**
 * TanStack Query hooks for the admin module (STRUCTURE §4). Flat file — well under the
 * ~400-line split threshold the bigger modules used.
 */

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  assignRole,
  createRole,
  createUser,
  getRole,
  getUser,
  listAuditLogs,
  listIndustryTemplates,
  listNumberSequences,
  listPermissions,
  listRoles,
  listUserRoles,
  listUsers,
  onboardTenant,
  type AuditLogFilters,
} from "@/modules/admin/api";
import type { OnboardTenantRequest, RoleAssign, RoleCreate, UserCreate } from "@/modules/admin/types";

// --- Users --------------------------------------------------------------------

export function useUsers() {
  return useInfiniteQuery({
    queryKey: ["admin", "users"],
    queryFn: ({ pageParam }) => listUsers(pageParam ? { cursor: pageParam } : {}),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export function useUser(userId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "user", userId],
    queryFn: () => getUser(userId as string),
    enabled: userId !== undefined,
  });
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserCreate) => createUser(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
  });
}

export function useUserRoles(userId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "user-roles", userId],
    queryFn: () => listUserRoles(userId as string),
    enabled: userId !== undefined,
  });
}

export function useAssignRole(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoleAssign) => assignRole(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "user-roles", userId] });
    },
  });
}

// --- Roles + permission catalog -----------------------------------------------

export function useRoles() {
  return useInfiniteQuery({
    queryKey: ["admin", "roles"],
    queryFn: ({ pageParam }) => listRoles(pageParam ? { cursor: pageParam } : {}),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

/** One page of roles for the assign-role picker (mirrors useVendorOptions). */
export function useRoleOptions() {
  return useQuery({
    queryKey: ["admin", "roles", "options"],
    queryFn: () => listRoles({ limit: 100 }),
    staleTime: 60_000,
  });
}

export function useRole(roleId: string | undefined) {
  return useQuery({
    queryKey: ["admin", "role", roleId],
    queryFn: () => getRole(roleId as string),
    enabled: roleId !== undefined,
  });
}

export function useCreateRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoleCreate) => createRole(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
    },
  });
}

export function usePermissionCatalog() {
  return useQuery({
    queryKey: ["admin", "permissions"],
    queryFn: () => listPermissions(),
    staleTime: 5 * 60_000, // the catalog is code-defined; it changes on deploy, not per-session
  });
}

// --- Audit viewer --------------------------------------------------------------

export function useAuditLogs(filters: Omit<AuditLogFilters, "cursor"> = {}) {
  return useInfiniteQuery({
    queryKey: ["admin", "audit-logs", filters],
    queryFn: ({ pageParam }) =>
      listAuditLogs({ ...filters, ...(pageParam ? { cursor: pageParam } : {}) }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

// --- Number sequences -----------------------------------------------------------

export function useNumberSequences() {
  return useInfiniteQuery({
    queryKey: ["admin", "number-sequences"],
    queryFn: ({ pageParam }) => listNumberSequences(pageParam ? { cursor: pageParam } : {}),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

// --- Onboarding wizard -----------------------------------------------------------

export function useIndustryTemplates() {
  return useQuery({
    queryKey: ["admin", "industry-templates"],
    queryFn: () => listIndustryTemplates(),
    staleTime: 5 * 60_000, // shipped YAML files — immutable per deploy
  });
}

export function useOnboardTenant() {
  return useMutation({
    mutationFn: (payload: OnboardTenantRequest) => onboardTenant(payload),
  });
}
