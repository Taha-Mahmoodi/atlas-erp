"""Admin HTTP layer (PLAN 14.3, thin): parse -> call admin.service/queries -> return schema.

REST under ``/api/v1/admin`` — the admin surface over EXISTING core tables (no new table,
no migration):

* Users   — GET/POST ``/users``, GET ``/users/{id}`` (with roles), POST ``/users/assign-role``.
* Roles   — GET/POST ``/roles``, GET ``/roles/{id}`` (with permissions).
* Catalog — GET ``/permissions`` (the global grantable permission set).
* Keys    — GET/POST ``/api-keys``, POST ``/api-keys/{id}/revoke`` (machine credentials).
* Audit   — GET ``/audit-logs`` (read-only viewer, filterable).
* Numbers — GET ``/number-sequences`` (read-only viewer).

Exchange rates and tax codes are NOT here: finance already ships them at ``/api/v1/finance``
(``/exchange-rates`` + ``/currencies`` under ``finance.fx.manage``; ``/tax-codes`` under
``finance.tax.*``). Re-exposing them under /admin would force admin to import finance's service
(STRUCTURE §5 violation) and duplicate an existing API — so admin cross-links them in docs only.

Writes reuse admin.service and commit through ``run_in_uow`` (D-011) so audit rides the same
transaction; write results are validated into their Read schema AFTER the uow commits. Reads are
cursor-paginated (D-014). RBAC (D-009): users/roles guarded by the existing ``admin.user.manage`` /
``admin.role.manage`` keys, the audit viewer by ``admin.audit.read``, the number-sequence viewer by
``admin.numbering.read``, machine credentials by ``admin.apikey.manage``. STRUCTURE §5: this router
imports core + admin only.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, Depends

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.exceptions import NotFoundError
from app.core.models import ApiKey
from app.core.pagination import CursorParams, cursor_params, map_page
from app.core.rbac import (
    ADMIN_APIKEY_MANAGE,
    ADMIN_AUDIT_READ,
    ADMIN_NUMBERING_READ,
    ADMIN_ROLE_MANAGE,
    ADMIN_USER_MANAGE,
    require_permission,
)
from app.core.schemas import Page
from app.modules.admin import queries, service
from app.modules.admin.schemas import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyRead,
    AuditLogRead,
    NumberSequenceRead,
    PermissionRead,
    RoleAssign,
    RoleCreate,
    RoleRead,
    RoleWithPermissions,
    UserCreate,
    UserRead,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

CursorParamsDep = Depends(cursor_params)


async def _commit[T](session: SessionDep, work: Callable[[], Awaitable[T]]) -> T:
    """Run a service call inside the D-011 uow and return its ORM result, refreshing it inside
    the work so server defaults materialize in the async context (the finance-router pattern)."""
    holder: list[T] = []

    async def _work() -> None:
        result = await work()
        await session.refresh(result)
        holder.append(result)

    await run_in_uow(session, _work)
    return holder[0]


def _role_with_permissions(role: object, permissions: list[str]) -> RoleWithPermissions:
    """Serialize a Role ORM row + its permission keys into the detail schema. The base fields
    come from the ORM object (from_attributes); permissions are attached from the grouped query
    since they are not a mapped column."""
    base = RoleRead.model_validate(role)
    return RoleWithPermissions(**base.model_dump(), permissions=permissions)


# --- Users --------------------------------------------------------------------


@router.get(
    "/users",
    response_model=Page[UserRead],
    dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))],
)
async def list_users(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[UserRead]:
    page = await queries.list_users(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, UserRead)


@router.post(
    "/users",
    response_model=UserRead,
    status_code=201,
    dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))],
)
async def create_user(
    payload: UserCreate, current: CurrentUserDep, session: SessionDep
) -> UserRead:
    """Create a user in the caller's tenant, reusing service.provision_user (it hashes the
    plaintext with argon2id, D-008). provision_user flushes but does not refresh, so _commit
    refreshes for server defaults (is_active/created_at)."""
    user = await _commit(
        session,
        lambda: service.provision_user(
            session,
            current.tenant_id,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
        ),
    )
    return UserRead.model_validate(user)


@router.get(
    "/users/{user_id}",
    response_model=UserRead,
    dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))],
)
async def get_user(
    user_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> UserRead:
    user = await queries.get_user(session, current.tenant_id, user_id)
    if user is None:
        raise NotFoundError(message="User not found", code="admin.user_not_found")
    return UserRead.model_validate(user)


@router.get(
    "/users/{user_id}/roles",
    response_model=list[RoleRead],
    dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))],
)
async def get_user_roles(
    user_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> list[RoleRead]:
    """The roles assigned to one user (one JOIN, no N+1). 404s an unknown user so an empty
    list unambiguously means 'exists but has no roles'."""
    user = await queries.get_user(session, current.tenant_id, user_id)
    if user is None:
        raise NotFoundError(message="User not found", code="admin.user_not_found")
    roles = await queries.get_user_roles(session, current.tenant_id, user_id)
    return [RoleRead.model_validate(role) for role in roles]


@router.post(
    "/users/assign-role",
    status_code=201,
    dependencies=[Depends(require_permission(ADMIN_USER_MANAGE))],
)
async def assign_role(
    payload: RoleAssign, current: CurrentUserDep, session: SessionDep
) -> dict[str, str]:
    """Assign a role to a user, reusing service.assign_role (it evicts the RBAC cache so the new
    permissions appear on the assignee's next request). Both ids are tenant-scoped by the D-007
    filter; a role/user from another tenant simply is not found. token_version 0 is passed to the
    cache eviction: on mismatch the stale entry expires within the 60s TTL (D-009)."""

    async def _work() -> None:
        await service.assign_role(
            session,
            current.tenant_id,
            payload.user_id,
            payload.role_id,
            token_version=0,
        )

    await run_in_uow(session, _work)
    return {"status": "assigned"}


# --- Roles --------------------------------------------------------------------


@router.get(
    "/roles",
    response_model=Page[RoleRead],
    dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
)
async def list_roles(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[RoleRead]:
    page = await queries.list_roles(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, RoleRead)


@router.post(
    "/roles",
    response_model=RoleWithPermissions,
    status_code=201,
    dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
)
async def create_role(
    payload: RoleCreate, current: CurrentUserDep, session: SessionDep
) -> RoleWithPermissions:
    """Create a role + grant the named permission keys, reusing service.create_role (it
    validates every key against the global catalog — an unknown key is a 422)."""
    role = await _commit(
        session,
        lambda: service.create_role(
            session, current.tenant_id, payload.name, payload.permissions
        ),
    )
    return _role_with_permissions(role, sorted(dict.fromkeys(payload.permissions)))


@router.get(
    "/roles/{role_id}",
    response_model=RoleWithPermissions,
    dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
)
async def get_role(
    role_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> RoleWithPermissions:
    """One role with its granted permission keys, attached N+1-free (one role -> one grants
    query). 404s an unknown role."""
    role = await queries.get_role(session, current.tenant_id, role_id)
    if role is None:
        raise NotFoundError(message="Role not found", code="admin.role_not_found")
    grouped = await queries.permission_keys_for_roles(
        session, current.tenant_id, [role.id]
    )
    return _role_with_permissions(role, grouped.get(role.id, []))


# --- Permission catalog -------------------------------------------------------


@router.get(
    "/permissions",
    response_model=list[PermissionRead],
    dependencies=[Depends(require_permission(ADMIN_ROLE_MANAGE))],
)
async def list_permissions(
    current: CurrentUserDep, session: SessionDep
) -> list[PermissionRead]:
    """The global permission catalog — the grantable universe a role editor picks from (D-009).
    Reading it is part of role management, so it shares the ``admin.role.manage`` guard."""
    permissions = await queries.list_permissions(session)
    return [PermissionRead.model_validate(permission) for permission in permissions]


# --- Machine credentials (spec Q1) --------------------------------------------


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
    dependencies=[Depends(require_permission(ADMIN_APIKEY_MANAGE))],
)
async def create_api_key(
    payload: ApiKeyCreate, current: CurrentUserDep, session: SessionDep
) -> ApiKeyCreated:
    """Issue a key bound to one of the tenant's users. The full key is in this response and
    nowhere else — only its sha256 is stored. An unknown scope is a 422 (D-009); a user id
    from another tenant is simply not found under the D-007 filter."""
    if await queries.get_user(session, current.tenant_id, payload.user_id) is None:
        raise NotFoundError(message="User not found", code="admin.user_not_found")
    holder: list[tuple[ApiKey, str]] = []

    async def _work() -> None:
        holder.append(await service.create_api_key(session, current.tenant_id, payload))

    await run_in_uow(session, _work)
    key, full_key = holder[0]
    return ApiKeyCreated(**ApiKeyRead.model_validate(key).model_dump(), key=full_key)


@router.get(
    "/api-keys",
    response_model=Page[ApiKeyRead],
    dependencies=[Depends(require_permission(ADMIN_APIKEY_MANAGE))],
)
async def list_api_keys(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[ApiKeyRead]:
    page = await queries.list_api_keys(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, ApiKeyRead)


@router.post(
    "/api-keys/{key_id}/revoke",
    response_model=ApiKeyRead,
    dependencies=[Depends(require_permission(ADMIN_APIKEY_MANAGE))],
)
async def revoke_api_key(
    key_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> ApiKeyRead:
    """Revoke a key; effective on the credential's very next request. Idempotent by design:
    revoking twice returns 200 with the FIRST timestamp, so a client retry is not an error."""
    key = await queries.get_api_key(session, current.tenant_id, key_id)
    if key is None:
        raise NotFoundError(message="API key not found", code="admin.api_key_not_found")
    await run_in_uow(session, lambda: service.revoke_api_key(session, key))
    return ApiKeyRead.model_validate(key)


# --- Audit viewer (read-only) -------------------------------------------------


@router.get(
    "/audit-logs",
    response_model=Page[AuditLogRead],
    dependencies=[Depends(require_permission(ADMIN_AUDIT_READ))],
)
async def list_audit_logs(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
    entity_table: str | None = None,
    entity_id: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> Page[AuditLogRead]:
    """The tenant's audit trail (D-010), newest-first, filterable by entity / actor / action /
    date range. Tenant-isolated by the D-007 filter — a tenant can only read its OWN rows. No
    extra masking beyond what capture already excluded (password_hash is never in a diff)."""
    page = await queries.list_audit_logs(
        session,
        current.tenant_id,
        cursor=params.cursor,
        limit=params.limit,
        entity_table=entity_table,
        entity_id=entity_id,
        actor_user_id=actor_user_id,
        action=action,
        created_from=created_from,
        created_to=created_to,
    )
    return map_page(page, AuditLogRead)


# --- Number-sequence viewer (read-only) ---------------------------------------


@router.get(
    "/number-sequences",
    response_model=Page[NumberSequenceRead],
    dependencies=[Depends(require_permission(ADMIN_NUMBERING_READ))],
)
async def list_number_sequences(
    current: CurrentUserDep,
    session: SessionDep,
    params: CursorParams = CursorParamsDep,
) -> Page[NumberSequenceRead]:
    # ponytail: read-only viewer, no reset/adjust write. Mutating next_value would open a gap
    # (or a duplicate) in the gapless numbering D-012 guarantees, so exposing it is a foot-gun
    # with no v1 need (YAGNI). Add a guarded, audited adjust endpoint only if a real correction
    # workflow demands it.
    page = await queries.list_number_sequences(
        session, current.tenant_id, cursor=params.cursor, limit=params.limit
    )
    return map_page(page, NumberSequenceRead)
