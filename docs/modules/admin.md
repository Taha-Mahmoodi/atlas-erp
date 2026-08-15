# Admin (`backend/app/modules/admin/`)

The admin module is the **tenant-administration surface** (PLAN 14 / Phase 14). It owns the
tenancy root + per-tenant settings and the user/role **provisioning service**, and — as of PLAN
14.3 — the tenant-admin **API**: user/role management, a read-only audit viewer, and a read-only
number-sequence viewer. Everything in 14.3 is **endpoints over EXISTING core tables** — no new
table, no migration.

The normative design lives in **D-062** ([DECISIONS.md](../../DECISIONS.md)); this guide is the
operator/contributor map. RBAC keys are **D-009**; audit is **D-010**; numbering is **D-012**.

## Status

**PLAN 14.3 is COMPLETE** — the admin router + schemas + read queries over users/roles, the audit
viewer, and the number-sequence viewer.

| File | Concern |
|---|---|
| `models.py` | `Tenant` (`adm_tenants`, the tenancy root) + `TenantSetting` (`adm_tenant_settings`) |
| `service.py` | user/role writes: `provision_user`, `provision_tenant`, `create_role`, `assign_role`, `grant_admin_role`, `find_user_by_email`, `find_tenant_by_slug` |
| `queries.py` | the read side: `list_users`, `get_user`/`get_user_roles`, `list_roles`/`get_role`, `permission_keys_for_roles`, `list_permissions`, `list_audit_logs`, `list_number_sequences` |
| `schemas.py` | the wire shapes (`UserRead`/`UserCreate`, `RoleRead`/`RoleWithPermissions`/`RoleCreate`/`RoleAssign`, `PermissionRead`, `AuditLogRead`, `NumberSequenceRead`) |
| `router.py` | the `/api/v1/admin` endpoints (below) |

The user/role/permission/audit/number-sequence **tables** all live in `core/` (Phase 3): `core_users`,
`core_roles`, `core_permissions`, `core_role_permissions`, `core_user_roles` (core/models.py),
`core_audit_log` (core/models.py + core/audit.py), `core_number_sequences` (core/numbering.py). The
admin module reads them through its own `queries.py` and writes through its own `service.py` — it
imports **core + its own module only** (STRUCTURE §5; grep-verified). It never imports another
module's service.

## Endpoints (`/api/v1/admin`)

All are tenant-scoped (the D-007 filter isolates every read to the caller's tenant), RBAC-guarded,
and — for lists — keyset-paginated (D-014, `?cursor=&limit=`), N+1-free (≤3 queries/list).

### Users & roles

| Method + path | Guard | Purpose |
|---|---|---|
| `GET /users` | `admin.user.manage` | list the tenant's users (credentials excluded) |
| `POST /users` | `admin.user.manage` | create a user (reuses `service.provision_user`, argon2id) |
| `GET /users/{id}` | `admin.user.manage` | one user (404 `admin.user_not_found`) |
| `GET /users/{id}/roles` | `admin.user.manage` | the user's assigned roles (one JOIN) |
| `POST /users/assign-role` | `admin.user.manage` | assign a role to a user (evicts the RBAC cache) |
| `GET /roles` | `admin.role.manage` | list the tenant's roles |
| `POST /roles` | `admin.role.manage` | create a role + grant permission keys (unknown key → 422 `rbac.unknown_permission`) |
| `GET /roles/{id}` | `admin.role.manage` | one role WITH its permission keys (404 `admin.role_not_found`) |
| `GET /permissions` | `admin.role.manage` | the **global** permission catalog (the grantable universe) |

Writes reuse `admin.service` and commit through `run_in_uow` (D-011) so the audit rows ride the same
transaction. The role→permission and user→role attaches are answered with a single JOIN + in-Python
grouping keyed on the parent id, so a page of roles (or one user's roles) costs **one** extra query,
not N.

### Machine credentials (D-069)

| Method + path | Guard | Purpose |
|---|---|---|
| `POST /api-keys` | `admin.apikey.manage` | mint a key bound to one of the tenant's users; the 201 body carries the full key **once** (unknown scope → 422 `rbac.unknown_permission`, foreign user → 404 `admin.user_not_found`) |
| `GET /api-keys` | `admin.apikey.manage` | list the tenant's keys, newest first — never the secret or its digest |
| `POST /api-keys/{id}/revoke` | `admin.apikey.manage` | revoke; idempotent, effective on the key's next request (404 `admin.api_key_not_found`) |

Only the key's SHA-256 is stored, so a lost key is re-issued, never recovered. Scopes *intersect* the
bound user's resolved permissions (D-009) — a key can only narrow, never widen. The operator flow,
rotation procedure and rate limit are in [docs/api.md](../api.md).

### Audit viewer (read-only)

`GET /audit-logs` — guarded by `admin.audit.read`. Newest-first, keyset-paginated, filterable by
`entity_table`, `entity_id`, `actor_user_id`, `action`, `created_from`, `created_to`. Tenant-isolated
by the D-007 filter — a tenant can only ever read its **own** rows. The `diff` is returned as
captured; no extra masking is applied because capture already excludes sensitive fields (e.g.
`password_hash` is never in a diff, D-010). The two hot filter paths are covered by the composite
indexes on `core_audit_log` (`(tenant_id, entity_table, entity_id)` and `(tenant_id, created_at)`),
so filtered reads seek rather than scan.

### Number-sequence viewer (read-only)

`GET /number-sequences` — guarded by `admin.numbering.read`. Lists the tenant's `NumberSequence` rows
(name, prefix, padding, `next_value`, `year_reset`, `current_year`), keyset-paginated by name.

**Read-only by design (ponytail):** there is deliberately **no** reset/adjust-current-value write.
Mutating `next_value` out of band would open a gap (or a duplicate) in the gapless numbering D-012
guarantees, so exposing it is a foot-gun with no v1 need (YAGNI). A guarded, audited adjust endpoint
can be added later if a real correction workflow demands it.

## Exchange rates & tax codes live in Finance, not here

These two PLAN-14.3 requirements were **already shipped by the finance module** and are **not**
re-exposed under `/admin` — doing so would force `admin → finance/service` (a STRUCTURE §5 violation)
and duplicate an existing API. Manage them at:

| Concern | Endpoints |
|---|---|
| Exchange rates | `GET`/`POST /api/v1/finance/exchange-rates` (guard `finance.fx.manage`) |
| Currencies | `GET`/`POST /api/v1/finance/currencies` (guard `finance.fx.manage`) |
| FX posting defaults / revaluation | `GET`/`PUT /api/v1/finance/posting-defaults`, `GET`/`POST /api/v1/finance/fx-revaluation-runs` |
| Tax codes | `GET`/`POST /api/v1/finance/tax-codes`, `GET`/`PATCH /api/v1/finance/tax-codes/{id}` (guards `finance.tax.read`/`.manage`) |

See [finance.md](finance.md) for the full FX (D-019) and tax-code surfaces.

## Permission keys

The admin keys are **core RBAC keys** declared in `core/rbac.py` (registered at import, seeded by
`sync_permission_catalog`): `admin.user.manage`, `admin.role.manage`, `admin.audit.read`,
`admin.tenant.manage`, `admin.numbering.read` (the read-only number-sequence viewer's own key,
added in 14.3) and `admin.apikey.manage`.

`grant_admin_role` creates the tenant's `Administrator` role from these six by default — the role
seed and the test factories get. **Onboarding overrides it** (#165): a tenant provisioned through
the wizard gets an Administrator holding the *whole synced catalog minus the platform-only keys*,
today just `onboarding.tenant.create`. The six admin keys grant no read on the COA, tax codes or
UoMs the industry template instantiates, so the tenant's first human could not see its own
company's masters. The grant is computed from `catalog_keys()`, not curated, so a module shipping a
new permission does not silently re-open the gap. `grant_admin_role` reuses an existing role of the
same name untouched, so a narrowed Administrator is never re-widened behind the tenant's back.
