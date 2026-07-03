/**
 * Placeholder for a module's route before its UI lands (PLAN 15.4-15.12 build it out module
 * by module). Distinguishes "not built yet" from "you don't have access" so a mistyped or
 * shared URL is honest either way.
 */

import { useParams } from "@tanstack/react-router";

import { hasModuleAccess, useMe } from "@/lib/session";
import { moduleByKey } from "@/shell/moduleRegistry";

export function ModulePlaceholderPage() {
  const { moduleKey } = useParams({ strict: false });
  const me = useMe();
  const entry = moduleKey ? moduleByKey(moduleKey) : undefined;

  if (!entry) {
    return <p className="text-sm text-ink-muted">Unknown module.</p>;
  }
  const permissions = me.data?.permissions ?? [];
  if (!me.isPending && !hasModuleAccess(permissions, entry.permissionPrefix)) {
    return (
      <p role="alert" className="text-sm text-danger">
        You don't have access to {entry.label}.
      </p>
    );
  }
  return (
    <div>
      <h1 className="text-xl font-semibold text-ink">{entry.label}</h1>
      <p className="mt-2 text-sm text-ink-muted">
        {entry.description}. This module's UI ships in a later phase of PLAN 15.
      </p>
    </div>
  );
}
