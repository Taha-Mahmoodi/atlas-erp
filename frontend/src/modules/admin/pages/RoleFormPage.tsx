/**
 * Create a role and grant it permission keys (STRUCTURE §4). The grantable universe comes
 * from GET /admin/permissions (the global catalog, D-009); keys are grouped by their module
 * prefix so a long flat list stays scannable. Roles are create-only in v1 — the backend has
 * no role-update endpoint (permissions change by creating a new role).
 */

import { useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { useCreateRole, usePermissionCatalog } from "@/modules/admin/hooks";
import type { Permission } from "@/modules/admin/types";

function groupByModule(catalog: Permission[]): Map<string, Permission[]> {
  const groups = new Map<string, Permission[]>();
  for (const permission of catalog) {
    const prefix = permission.key.split(".")[0] ?? permission.key;
    const bucket = groups.get(prefix);
    if (bucket) bucket.push(permission);
    else groups.set(prefix, [permission]);
  }
  return groups;
}

export function RoleFormPage() {
  const navigate = useNavigate();
  const catalog = usePermissionCatalog();
  const createRole = useCreateRole();

  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const groups = useMemo(() => groupByModule(catalog.data ?? []), [catalog.data]);

  const toggle = (key: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const submit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Role name is required.");
      return;
    }
    try {
      const created = await createRole.mutateAsync({
        name: name.trim(),
        permissions: [...selected].sort(),
      });
      void navigate({ to: "/admin/roles/$roleId", params: { roleId: created.id } });
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to create the role."));
    }
  };

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">New role</h1>
      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <div className="mt-6">
        <label htmlFor="role-name" className="block text-xs font-medium text-ink-muted">
          Role name
        </label>
        <input
          id="role-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 w-full rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink placeholder:text-ink-muted hover:border-ink-faint"
          placeholder="e.g. Warehouse clerk"
        />
      </div>

      <h2 className="mt-6 text-sm font-semibold text-ink">
        Permissions{" "}
        <span className="font-normal text-ink-muted">({selected.size} selected)</span>
      </h2>
      {catalog.isPending && <p className="mt-2 text-sm text-ink-muted">Loading the permission catalog…</p>}
      {catalog.isError && (
        <p role="alert" className="mt-2 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {getErrorMessage(catalog.error, "Unable to load the permission catalog.")}
        </p>
      )}
      <div className="mt-2 space-y-4">
        {[...groups.entries()].map(([module, permissions]) => (
          <fieldset key={module} className="rounded-card border border-line bg-surface p-4 shadow-card">
            <legend className="px-1 text-xs font-semibold uppercase tracking-[0.04em] text-ink-muted">
              {module}
            </legend>
            <div className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {permissions.map((permission) => (
                <label key={permission.key} className="flex items-start gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={selected.has(permission.key)}
                    onChange={() => toggle(permission.key)}
                    className="mt-0.5"
                  />
                  <span>
                    <code className="text-xs">{permission.key}</code>
                    {permission.description && (
                      <span className="block text-xs text-ink-muted">{permission.description}</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>

      <div className="mt-6">
        <button
          type="button"
          disabled={createRole.isPending}
          onClick={() => void submit()}
          className="btn-ink"
        >
          {createRole.isPending ? "Creating…" : "Create role"}
        </button>
      </div>
    </div>
  );
}
