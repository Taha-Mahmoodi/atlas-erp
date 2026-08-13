/**
 * React-facing session glue. `lib/auth.ts` stays framework-agnostic (plain functions +
 * a subscriber set); this file is the only place that turns it into hooks, and owns the
 * `/auth/me` query that resolves the caller's permissions (the source of "role" for the
 * role-based shell — STRUCTURE §4, CLAUDE.md's Fiori-inspired home pages).
 */

import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { api } from "@/lib/apiClient";
import { isAuthenticated, onSessionChange } from "@/lib/auth";

export function useIsAuthenticated(): boolean {
  return useSyncExternalStore(onSessionChange, isAuthenticated, isAuthenticated);
}

export interface Me {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  permissions: string[];
}

/** The caller's identity + permissions — enabled only once a session exists. */
export function useMe() {
  const authenticated = useIsAuthenticated();
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<Me>("/auth/me"),
    enabled: authenticated,
    staleTime: Infinity, // permissions don't change mid-session; a fresh login refetches
  });
}

/** Whether any of the caller's permissions fall under a module's namespace ("finance."). */
export function hasModuleAccess(permissions: string[], modulePrefix: string): boolean {
  return permissions.some((permission) => permission.startsWith(modulePrefix));
}
