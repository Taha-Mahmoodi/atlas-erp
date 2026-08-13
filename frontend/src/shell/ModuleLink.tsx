/**
 * Navigates to a module's real static route when one is registered, else the dynamic
 * `/$moduleKey` placeholder (router.tsx). Routing to the SAME literal path two different ways
 * (a dynamic template's generated "/finance" vs the static "/finance" route) is what TanStack
 * Router warns about — this is the one place that ambiguity gets resolved, via a switch over
 * the small `StaticModuleRoute` union rather than a cast, so it stays type-checked.
 */

import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

import type { ModuleEntry } from "@/shell/moduleRegistry";

export function ModuleLink({
  entry,
  className,
  children,
}: {
  entry: ModuleEntry;
  className?: string;
  children: ReactNode;
}) {
  switch (entry.route) {
    case "finance":
      return (
        <Link to="/finance" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "inventory":
      return (
        <Link to="/inventory" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "procurement":
      return (
        <Link to="/procurement" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "sales":
      return (
        <Link to="/sales" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "reporting":
      return (
        <Link to="/reporting" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "admin":
      return (
        <Link to="/admin" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    case "manufacturing":
      return (
        <Link to="/manufacturing" {...(className ? { className } : {})}>
          {children}
        </Link>
      );
    default:
      return (
        <Link
          to="/$moduleKey"
          params={{ moduleKey: entry.key }}
          {...(className ? { className } : {})}
        >
          {children}
        </Link>
      );
  }
}
