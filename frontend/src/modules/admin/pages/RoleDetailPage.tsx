/**
 * Role detail (STRUCTURE §4): the role's fields plus its granted permission keys, grouped
 * by module prefix. Read-only — the backend has no role-update endpoint in v1.
 */

import { useParams } from "@tanstack/react-router";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { useRole } from "@/modules/admin/hooks";

export function RoleDetailPage() {
  const { roleId } = useParams({ strict: false });
  const role = useRole(roleId);

  if (role.isPending) return <p className="text-sm text-ink-muted">Loading…</p>;
  if (role.isError || !role.data) {
    return (
      <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
        {getErrorMessage(role.error, "Role not found.")}
      </p>
    );
  }

  const groups = new Map<string, string[]>();
  for (const key of role.data.permissions) {
    const prefix = key.split(".")[0] ?? key;
    const bucket = groups.get(prefix);
    if (bucket) bucket.push(key);
    else groups.set(prefix, [key]);
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-[22px] font-[650] tracking-[-0.01em] text-ink">{role.data.name}</h1>
      <div className="mt-6 rounded-card border border-line bg-surface p-4 shadow-card">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
          <dt className="text-ink-muted">Description</dt>
          <dd className="text-ink">{role.data.description ?? "—"}</dd>
          <dt className="text-ink-muted">Kind</dt>
          <dd className="text-ink">{role.data.is_system ? "System" : "Custom"}</dd>
          <dt className="text-ink-muted">Created</dt>
          <dd className="text-ink">{formatDateTime(role.data.created_at)}</dd>
        </dl>
      </div>

      <h2 className="mt-8 text-sm font-semibold text-ink">
        Permissions <span className="font-normal text-ink-muted">({role.data.permissions.length})</span>
      </h2>
      {role.data.permissions.length === 0 && (
        <p className="mt-2 text-sm text-ink-muted">This role grants no permissions.</p>
      )}
      <div className="mt-2 space-y-4">
        {[...groups.entries()].map(([module, keys]) => (
          <section key={module} className="rounded-card border border-line bg-surface p-4 shadow-card">
            <h3 className="text-xs font-semibold uppercase tracking-[0.04em] text-ink-muted">{module}</h3>
            <ul className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
              {keys.map((key) => (
                <li key={key}>
                  <code className="text-xs text-ink">{key}</code>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
