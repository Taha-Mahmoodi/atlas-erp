/**
 * Navigates to a module's real static route when one is registered, else the dynamic
 * `/$moduleKey` placeholder (router.tsx). Routing to the SAME literal path two different ways
 * (a dynamic template's generated "/finance" vs the static "/finance" route) is what TanStack
 * Router warns about — this is the one place that ambiguity gets resolved, via a switch over
 * the small `StaticModuleRoute` union rather than a cast, so it stays type-checked.
 *
 * `moduleLinkProps` exposes the same switch to callers that navigate imperatively (the ⌘K
 * palette), so there is still exactly one mapping from module → route in the codebase.
 */

import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import type { ModuleEntry } from "@/shell/moduleRegistry";

export function moduleLinkProps(entry: ModuleEntry) {
  switch (entry.route) {
    case "finance":
      return { to: "/finance" } as const;
    case "inventory":
      return { to: "/inventory" } as const;
    case "procurement":
      return { to: "/procurement" } as const;
    case "sales":
      return { to: "/sales" } as const;
    case "reporting":
      return { to: "/reporting" } as const;
    case "admin":
      return { to: "/admin" } as const;
    case "manufacturing":
      return { to: "/manufacturing" } as const;
    case "quality":
      return { to: "/quality" } as const;
    case "maintenance":
      return { to: "/maintenance" } as const;
    case "projects":
      return { to: "/projects" } as const;
    case "crm":
      return { to: "/crm" } as const;
    case "hr":
      return { to: "/hr" } as const;
    default:
      return { to: "/$moduleKey", params: { moduleKey: entry.key } } as const;
  }
}

export function ModuleLink({
  entry,
  className,
  children,
}: {
  entry: ModuleEntry;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link {...moduleLinkProps(entry)} {...(className ? { className } : {})}>
      {children}
    </Link>
  );
}
