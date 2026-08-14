/**
 * User workbench (STRUCTURE §4): identity fields, assigned roles, and an assign-role
 * action. Role assignment takes effect on the assignee's next request (D-009 cache
 * eviction; a stale entry expires within the 60s TTL).
 */

import { Link, useParams } from "@tanstack/react-router";
import { useState } from "react";

import { getErrorMessage } from "@/lib/apiClient";
import { formatDateTime } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";
import { useAssignRole, useRoleOptions, useUser, useUserRoles } from "@/modules/admin/hooks";

export function UserDetailPage() {
  const { userId } = useParams({ strict: false });
  const user = useUser(userId);
  const roles = useUserRoles(userId);
  const roleOptions = useRoleOptions();
  const assignRole = useAssignRole(userId ?? "");

  const [roleId, setRoleId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const assignedIds = new Set((roles.data ?? []).map((role) => role.id));
  const assignable = (roleOptions.data?.items ?? []).filter((role) => !assignedIds.has(role.id));

  const assign = async () => {
    if (!roleId || !userId) return;
    setError(null);
    try {
      await assignRole.mutateAsync({ user_id: userId, role_id: roleId });
      setRoleId("");
    } catch (caught) {
      setError(getErrorMessage(caught, "Unable to assign the role."));
    }
  };

  if (user.isPending) return <p className="text-[13px] text-ink-muted">Loading…</p>;
  if (user.isError || !user.data) {
    return (
      <p role="alert" className="rounded-control bg-danger-tint px-3 py-2 text-sm text-danger">
        {getErrorMessage(user.error, "User not found.")}
      </p>
    );
  }

  return (
    <div className="mx-auto max-w-2xl">
      <header className="mb-6">
        <p className="text-[12px] text-ink-muted">
          <Link to="/admin/users" className="hover:text-ink">
            Users
          </Link>{" "}
          / <span className="text-ink">{user.data.email}</span>
        </p>
        <h1 className="mt-1.5 text-[22px] font-[650] tracking-[-0.01em] text-ink">{user.data.email}</h1>
      </header>
      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 rounded-card border border-line bg-surface px-[18px] py-4 shadow-card sm:grid-cols-4">
        <div>
          <dt className="mono-caps text-ink-muted">Full name</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{user.data.full_name ?? "—"}</dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Status</dt>
          <dd className="mt-1.5 text-[13px] text-ink">
            <StatusPill status={user.data.is_active ? "ACTIVE" : "INACTIVE"} />
          </dd>
        </div>
        <div>
          <dt className="mono-caps text-ink-muted">Created</dt>
          <dd className="mt-1.5 text-[13px] text-ink">{formatDateTime(user.data.created_at)}</dd>
        </div>
      </dl>

      <h2 className="mt-8 mono-caps text-ink-muted">Roles</h2>
      {roles.isPending && <p className="mt-2 text-[13px] text-ink-muted">Loading roles…</p>}
      {roles.data && roles.data.length === 0 && (
        <p className="mt-2 text-sm text-ink-muted">No roles assigned yet — this user has no permissions.</p>
      )}
      <ul className="mt-2 space-y-2">
        {(roles.data ?? []).map((role) => (
          <li key={role.id} className="rounded-card border border-line bg-surface px-4 py-2 shadow-card">
            <Link
              to="/admin/roles/$roleId"
              params={{ roleId: role.id }}
              className="text-[12.5px] font-medium text-primary hover:underline"
            >
              {role.name}
            </Link>
            {role.description && <span className="ml-2 text-xs text-ink-muted">{role.description}</span>}
          </li>
        ))}
      </ul>

      {error && (
        <p role="alert" className="mt-4 rounded-control bg-danger-tint px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}
      <div className="mt-4 flex items-center gap-2">
        <label htmlFor="assign-role" className="text-xs font-medium text-ink-muted">
          Assign role
        </label>
        <select
          id="assign-role"
          value={roleId}
          onChange={(event) => setRoleId(event.target.value)}
          className="rounded-control border border-line bg-surface px-3 py-1.5 text-sm text-ink"
        >
          <option value="">Select…</option>
          {assignable.map((role) => (
            <option key={role.id} value={role.id}>
              {role.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={!roleId || assignRole.isPending}
          onClick={() => void assign()}
          className="btn-ink"
        >
          {assignRole.isPending ? "Assigning…" : "Assign"}
        </button>
      </div>
    </div>
  );
}
