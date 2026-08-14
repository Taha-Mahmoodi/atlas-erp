# Hospitality Build Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the hospitality vertical — a machine credential that lets a property's own website
call Atlas, then restaurant ordering, then rooms and folio — without weakening any existing
platform invariant.

**Architecture:** The property's website is an external API *client*; Atlas is the backend of
record and never serves a guest directly. Authentication is a scoped API key that resolves to a
dedicated service `User` row, branched inside the single existing principal builder
(`get_current_user`), so every downstream mechanism — tenancy, RBAC, masking, audit, idempotency —
is inherited unchanged. Restaurant ordering reuses the manufacturing BOM engine for recipes and the
job runner for depletion; rooms and folio reuse the finance receipt-clearing engine for deposits.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2, PostgreSQL
(SQLite for tests), pytest. Managed with `uv`.

**Spec:** [`docs/research/hospitality-industry-plan.md`](./hospitality-industry-plan.md) — the
proposal and its six resolved design questions. This plan argues from that document; executors read
both. Q1 is the spec for Phase 18 below.

## Status of this document

**This is a plan, not a commitment.** `PLAN.md`, `STRUCTURE.md` and `GITHUB-WORKFLOW.md` are
deliberately untouched, and no code accompanies it — the owner asked for a standalone plan to review
first. A prior session let a research doc drift into ticked `PLAN.md` phases and scaffold code
before it was fully reverted (PR #143); this stays on the safe side of that line. Promoting these
phases into `PLAN.md` is a separate, explicit decision.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied from the binding
project documents.

- **D-003 portability.** Models are PostgreSQL-first but the whole suite runs on SQLite. DB-level
  constraints must be portable (`CHECK`, not `EXCLUDE`/range types) or carry a documented
  Postgres-only guard.
- **D-007 tenancy.** Row-level `tenant_id` enforced by a non-bypassable ORM session filter reading a
  ContextVar, fail-closed when unset. `backend/app/core/tenancy.py:49-64` documents exactly four
  sanctioned `system_context()` bypass sites. **This plan adds none.**
- **D-009 RBAC.** Permissions are data; keys are code-declared in the catalog
  (`backend/app/core/rbac.py:47`). A tenant can never invent a key no code checks.
- **D-011 event bus.** In-process, synchronous, dispatched inside the same transaction; any handler
  failure rolls back everything.
- **D-013 idempotency.** Required on every endpoint creating a financial or stock document.
- **PERFORMANCE.md.** ≤3 queries per list request; 50 concurrent users on 4 vCPU / 8 GB.
  `backend/tests/conftest.py:140,160-163` states the budget counts the auth user load plus the page
  select with "one query of slack", and **that slack is a regression margin, not headroom.**
- **STRUCTURE.md.** 400-line Python cap. Module anatomy: `models/ schemas/ service/ router.py
  events.py queries.py constants.py`. Terminology lock: `item`, `vendor`, `customer`, `warehouse`,
  `journal entry`.
- **Definition of done** (CLAUDE.md §5): code written, tests passing, committed, logged in
  `PROGRESS.md` — plus, for endpoints, the PERFORMANCE.md §6 checklist.

---

# Roadmap

Three phases, sequenced so each ships something independently useful. Phase numbers are proposed,
not reserved.

| Phase | Deliverable | Core change? | Why this order |
|---|---|---|---|
| **18 — Machine credential** | Scoped API keys + admin endpoints + nginx rate limiting | **Yes** — the only one | Prerequisite for both modules, and independently valuable: `docs/research/s4hana-parity.md:247` already records "Released APIs and event-based integration" as a v1 scope cut, so this has a recorded home rather than being unplanned scope |
| **19 — Restaurant Ordering** | Menu availability, order tickets, ingredient depletion, settlement | No | Higher reuse (BOM engine, job runner), proves the website↔Atlas loop end to end, and the failure modes are cheaper than the hotel's |
| **20 — Rooms & Folio** | Reservations, overbooking guard, folio, advance deposits, night audit, business date | No — **but yes to shipped `finance`** | The hard half. Touches production finance code, so it goes last, on top of a credential and a proven client integration |

**Phase 18 is planned in full below.** Phases 19 and 20 get their own plans when 18 lands —
they are separate subsystems, each producing working software on its own, and detailed steps
written three phases ahead go stale before anyone reads them. What they contain is fixed by the
spec's Q2–Q6; what is *not* yet decided is the task decomposition, which depends on what Phase 18
actually teaches us.

**Not in any phase** (spec's out-of-scope list, unchanged): OTA/channel-manager sync, algorithmic
room pricing, loyalty programs, third-party delivery injection, KDS hardware, multi-property
reporting, any AI feature.

---

# Phase 18 — Machine credential

**Goal:** A property's website can call Atlas with a scoped, revocable API key that cannot exceed
its user's permissions and cannot reach another tenant.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/core/models.py` (modify) | Add `ApiKey` beside `RefreshSession` (`models.py:143-171`), which it structurally mirrors |
| `backend/app/core/auth.py` (modify) | Mint and parse the key string; reuse `sha256_hex` (`auth.py:43-45`) |
| `backend/app/core/deps.py` (modify) | One branch in `get_current_user` (`deps.py:64-112`) — the only principal builder |
| `backend/app/core/rbac.py` (modify) | Register `admin.apikey.manage` beside the existing `ADMIN_*` keys (`rbac.py:54+`) |
| `backend/app/modules/admin/` (modify) | Three endpoints: create, list, revoke |
| `backend/alembic/versions/` (create) | One migration for `core_api_keys` |
| `frontend/nginx.conf` (modify) | `limit_req_zone` keyed on the Authorization header |
| `backend/tests/core/test_api_keys.py` (create) | Auth, scoping, cross-tenant, revocation, expiry |
| `DECISIONS.md` (modify) | Record that bearer credentials now have two shapes, and why the tenant rides in the key |

## Interfaces produced by this phase

Later phases consume these; the names are fixed here.

```python
# backend/app/core/auth.py
def mint_api_key(tenant_ref: str) -> tuple[str, str]:
    """Returns (full_key, secret_sha256). full_key is shown ONCE and never stored."""

def parse_api_key(raw: str) -> tuple[str, str] | None:
    """Returns (tenant_ref, secret_sha256) or None if the string is not a well-formed key."""

# backend/app/core/models.py
class ApiKey(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "core_api_keys"
    user_id: Mapped[uuid.UUID]
    name: Mapped[str]
    prefix: Mapped[str]              # the non-secret lookup half, indexed
    secret_sha256: Mapped[str]       # unique
    scopes: Mapped[list[str] | None] # None = inherit the user's permissions unnarrowed
    expires_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
```

## Task 1: The `ApiKey` model and its migration

**Files:**
- Modify: `backend/app/core/models.py` (add after `RefreshSession`, which ends at line 171)
- Create: `backend/alembic/versions/<rev>_add_core_api_keys.py`
- Test: `backend/tests/core/test_api_keys.py`

**Interfaces:**
- Consumes: `UuidPKMixin`, `TenantMixin`, `TimestampMixin`, `tenant_unique()`, `tenant_fk()` — all
  already used by `RefreshSession` at `models.py:143-171`.
- Produces: the `ApiKey` model above.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/core/test_api_keys.py
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.models import ApiKey


@pytest.mark.asyncio
async def test_api_key_row_round_trips(session, tenant, user):
    """The model persists and reads back under the ordinary tenant filter (D-007)."""
    key = ApiKey(
        tenant_id=tenant.id,
        user_id=user.id,
        name="website",
        prefix="atk_abc123",
        secret_sha256="0" * 64,
        scopes=["inventory.item.read"],
        expires_at=datetime.now(UTC) + timedelta(days=365),
    )
    session.add(key)
    await session.flush()

    found = (await session.execute(select(ApiKey))).scalar_one()
    assert found.name == "website"
    assert found.scopes == ["inventory.item.read"]
    assert found.revoked_at is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -v`
Expected: FAIL — `ImportError: cannot import name 'ApiKey' from 'app.core.models'`

- [ ] **Step 3: Add the model**

Add to `backend/app/core/models.py`, immediately after `RefreshSession`:

```python
class ApiKey(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Machine credential for a first-party API client (the property's own website).

    Structurally mirrors RefreshSession: a hashed secret with revocation and expiry. Two
    deliberate differences. The secret is sha256, not argon2 — it is 256 bits of CSPRNG
    output, not a guessable password, and argon2id at the D-008 parameters costs "tens of
    ms" per the note at auth.py:68, which would blow the PERFORMANCE §5 budget on every
    request. And there is no last_used_at: writing one per request would add a write to
    every authenticated call for a statistic nobody reads.

    `scopes` is NULL for "inherit the user's permissions unnarrowed"; a non-null list may
    only ever NARROW them (see deps.py). Keys are bound to a real core_users row so the
    D-010 audit actor resolves — a synthetic principal id would insert cleanly and leave
    an unresolvable actor across the 13 submitted_by/approver_id sites that deliberately
    do not FK to core_users.
    """

    __tablename__ = "core_api_keys"
    __table_args__ = (
        tenant_unique(),
        tenant_fk("adm_tenants"),
        tenant_fk("core_users", "user_id"),
        # The auth hot path looks a key up by its hashed secret; uniqueness is also the
        # collision guard on mint.
        sa.UniqueConstraint("secret_sha256", name="uq_core_api_keys_secret_sha256"),
        sa.Index("ix_core_api_keys_tenant_id_user_id", "tenant_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    prefix: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    secret_sha256: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    scopes: Mapped[list[str] | None] = mapped_column(JsonList(), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
```

> **Before writing this:** confirm the JSON column helper's real name. `models.py` already
> stores JSON (the D-010 audit diff); use whatever type that column uses rather than
> introducing a second JSON convention. If it is a raw `sa.JSON`, use `sa.JSON` and drop the
> `JsonList()` above. D-003 requires the PostgreSQL/SQLite-portable variant.

- [ ] **Step 4: Generate and review the migration**

```bash
cd backend && ~/.local/bin/uv run alembic revision --autogenerate -m "add core_api_keys"
```

Open the generated file and verify: it creates `core_api_keys` only, the composite tenant FKs are
present, and it does **not** contain unrelated autogenerated drift. Alembic autogenerate routinely
emits spurious diffs; delete anything not about this table.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/models.py backend/alembic/versions/ backend/tests/core/test_api_keys.py
git commit -m "feat(core): add ApiKey model for first-party machine clients

Mirrors RefreshSession — hashed secret, revocation, expiry — with sha256
rather than argon2 because the secret is CSPRNG output, not a password,
and argon2 per request would blow the PERFORMANCE §5 budget."
```

## Task 2: Minting and parsing the key string

**Files:**
- Modify: `backend/app/core/auth.py` (add beside `sha256_hex` at `auth.py:43-45`)
- Test: `backend/tests/core/test_api_keys.py`

**Interfaces:**
- Consumes: `sha256_hex` (`auth.py:43-45`).
- Produces: `mint_api_key(tenant_ref) -> (full_key, secret_sha256)`,
  `parse_api_key(raw) -> (tenant_ref, secret_sha256) | None`.

- [ ] **Step 1: Write the failing test**

```python
def test_mint_and_parse_round_trip():
    full, digest = mint_api_key("acme")
    assert full.startswith("atk_acme_")
    parsed = parse_api_key(full)
    assert parsed is not None
    tenant_ref, parsed_digest = parsed
    assert tenant_ref == "acme"
    assert parsed_digest == digest


def test_mint_is_unpredictable():
    a, _ = mint_api_key("acme")
    b, _ = mint_api_key("acme")
    assert a != b


@pytest.mark.parametrize(
    "bad",
    ["", "atk_", "atk_acme", "notakey", "atk__secret", "Bearer atk_acme_x"],
)
def test_parse_rejects_malformed(bad):
    """A malformed credential must return None, never raise — deps.py turns None into a
    401, and an exception there would surface as a 500."""
    assert parse_api_key(bad) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -k "mint or parse" -v`
Expected: FAIL — `ImportError: cannot import name 'mint_api_key'`

- [ ] **Step 3: Implement**

Add to `backend/app/core/auth.py`:

```python
API_KEY_PREFIX = "atk"


def mint_api_key(tenant_ref: str) -> tuple[str, str]:
    """Mint a key for a tenant. Returns (full_key, secret_sha256).

    The full key is shown to the operator exactly once and never stored; only the digest
    is persisted, so a database leak cannot mint or replay a credential — the same
    argument as the refresh-jti hashing at auth.py:43.

    The tenant ref rides in the key so the D-007 ContextVar can be set BEFORE any lookup,
    which is what keeps the sanctioned system_context() bypass list at exactly four
    (tenancy.py:49-64). A forged ref simply finds no row.
    """
    secret = secrets.token_urlsafe(32)
    return f"{API_KEY_PREFIX}_{tenant_ref}_{secret}", sha256_hex(secret)


def parse_api_key(raw: str) -> tuple[str, str] | None:
    """Split a presented key into (tenant_ref, secret_sha256), or None if malformed."""
    parts = raw.split("_", 2)
    if len(parts) != 3:
        return None
    scheme, tenant_ref, secret = parts
    if scheme != API_KEY_PREFIX or not tenant_ref or not secret:
        return None
    return tenant_ref, sha256_hex(secret)
```

Add `import secrets` to the module imports if absent.

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -k "mint or parse" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/auth.py backend/tests/core/test_api_keys.py
git commit -m "feat(core): mint and parse scoped API keys

The tenant ref rides in the key string so the tenancy ContextVar can be set
before any lookup, keeping the sanctioned system_context() bypass list at
exactly four."
```

## Task 3: Authenticate a request with a key

**Files:**
- Modify: `backend/app/core/deps.py:64-112` (`get_current_user`)
- Test: `backend/tests/core/test_api_keys.py`

**Interfaces:**
- Consumes: `parse_api_key`, `ApiKey`, `resolve_permissions`, `current_tenant_id`,
  `current_permissions`, `actor_user_id_ctx` — all already imported by `deps.py`.
- Produces: no new public name. `get_current_user` gains a branch; all 436 `CurrentUserDep` call
  sites are untouched.

**Design note for the implementer.** `CurrentUser` (`deps.py:55-61`) carries
`token_version`, which is meaningless for a key. Set it from the loaded user row — the key's
revocation lives in `revoked_at`, and the user's `token_version` bump still works as a
kill-switch for both credential shapes.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_api_key_authenticates(client, tenant, service_user, api_key_factory):
    full, _ = await api_key_factory(user=service_user, scopes=["inventory.item.read"])
    response = await client.get(
        "/api/v1/inventory/items", headers={"Authorization": f"Bearer {full}"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_scopes_narrow_and_never_widen(client, service_user, api_key_factory):
    """The service user can post journals; the key is scoped to reads only, so the key
    cannot — a key may only ever narrow its user."""
    full, _ = await api_key_factory(user=service_user, scopes=["inventory.item.read"])
    response = await client.post(
        "/api/v1/finance/journal-entries",
        headers={"Authorization": f"Bearer {full}"},
        json={},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_key_cannot_reach_another_tenant(client, api_key_factory, other_tenant_item):
    full, _ = await api_key_factory(scopes=["inventory.item.read"])
    response = await client.get(
        f"/api/v1/inventory/items/{other_tenant_item.id}",
        headers={"Authorization": f"Bearer {full}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_revoked_key_is_rejected(client, api_key_factory):
    full, key = await api_key_factory(scopes=["inventory.item.read"], revoked=True)
    response = await client.get(
        "/api/v1/inventory/items", headers={"Authorization": f"Bearer {full}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_key_is_rejected(client, api_key_factory):
    full, _ = await api_key_factory(scopes=["inventory.item.read"], expired=True)
    response = await client.get(
        "/api/v1/inventory/items", headers={"Authorization": f"Bearer {full}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_forged_tenant_ref_is_rejected(client):
    response = await client.get(
        "/api/v1/inventory/items",
        headers={"Authorization": "Bearer atk_victim_forgedsecret"},
    )
    assert response.status_code == 401
```

Write `api_key_factory` as a fixture in this test module (or `conftest.py` if the existing fixtures
live there): it mints a key via `mint_api_key`, inserts an `ApiKey` row for the given user, and
returns `(full_key, row)`. Mirror the existing user/tenant fixtures rather than inventing a new
style.

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -v`
Expected: FAIL — the key is not recognised, so requests 401 where a 200 is expected.

- [ ] **Step 3: Implement the branch**

In `backend/app/core/deps.py`, inside `get_current_user`, after the `credentials is None` guard
(`deps.py:68-69`) and before `decode_token` (`deps.py:71`):

```python
    # Two credential shapes reach this function: a user access JWT and a machine API key
    # (D-0XX). They converge on the same CurrentUser, which is why no router, no
    # require_permission call, and no idempotency path needed changing.
    parsed = parse_api_key(credentials.credentials)
    if parsed is not None:
        return await _authenticate_api_key(session, *parsed)
```

Then add the helper below `get_current_user`:

```python
async def _authenticate_api_key(
    session: AsyncSession, tenant_ref: str, secret_sha256: str
) -> CurrentUser:
    """Resolve an API key to the same principal a JWT would produce.

    The tenant ContextVar is set from the key's own prefix before the lookup, exactly as
    deps.py:83 does from the JWT claim — so the key row is then read under the ordinary
    D-007 filter and a forged ref can only ever find nothing. No system_context() bypass.
    """
    tenant_id = await _tenant_id_for_ref(session, tenant_ref)
    if tenant_id is None:
        raise AuthError(message="Invalid API key", code="auth.invalid_token")
    current_tenant_id.set(tenant_id)

    # ONE query, joined: the PERFORMANCE budget counts the auth user load, and
    # tests/conftest.py:140 warns its one query of slack is a regression margin, not
    # headroom. A separate SELECT for the key would spend it.
    row = (
        await session.execute(
            select(User, ApiKey)
            .join(ApiKey, ApiKey.user_id == User.id)
            .where(ApiKey.secret_sha256 == secret_sha256)
        )
    ).one_or_none()
    if row is None:
        raise AuthError(message="Invalid API key", code="auth.invalid_token")

    user, key = row
    now = datetime.now(UTC)
    if (
        not user.is_active
        or key.revoked_at is not None
        or (key.expires_at is not None and key.expires_at <= now)
    ):
        raise AuthError(message="Invalid API key", code="auth.invalid_token")

    permissions = await resolve_permissions(
        session, user.id, user.tenant_id, user.token_version
    )
    if key.scopes is not None:
        # Intersection only: a key may narrow its user, never widen it (D-009).
        permissions = permissions & frozenset(key.scopes)

    current_permissions.set(permissions)
    actor_user_id_ctx.set(user.id)
    return CurrentUser(
        user_id=user.id,
        tenant_id=user.tenant_id,
        permissions=permissions,
        token_version=user.token_version,
    )
```

`_tenant_id_for_ref` resolves the tenant slug to its id. **Check first whether an existing helper
does this** — `security_router.py:80-130` already resolves `tenant_slug` on login; reuse it rather
than writing a second resolver. If it is inline there, extract it in this task and have both call
sites use it.

- [ ] **Step 4: Run to verify they pass**

Run: `cd backend && ~/.local/bin/uv run pytest tests/core/test_api_keys.py -v`
Expected: PASS (all six)

- [ ] **Step 5: Run the full suite and the query-budget tests**

Run: `cd backend && ~/.local/bin/uv run pytest -q`
Expected: 1786+ passed, 0 failed. **Pay attention to any query-count assertion failure** — it means
the joined lookup spent the slack, and the fix is the join, not raising the budget.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/deps.py backend/tests/core/test_api_keys.py
git commit -m "feat(core): authenticate requests with a scoped API key

One branch in the single principal builder, so all 436 CurrentUserDep call
sites, D-013 idempotency and D-009 masking are inherited unchanged. Scopes
intersect the user's permissions and can only narrow them."
```

## Task 4: Admin endpoints — create, list, revoke

**Files:**
- Modify: `backend/app/core/rbac.py` (register the key beside the `ADMIN_*` block at `rbac.py:54+`)
- Modify: `backend/app/modules/admin/` — router, schemas, service, per STRUCTURE module anatomy
- Test: `backend/tests/modules/admin/test_api_key_endpoints.py`

**Interfaces:**
- Consumes: `mint_api_key`, `ApiKey`, `require_permission`.
- Produces: `POST /api/v1/admin/api-keys`, `GET /api/v1/admin/api-keys`,
  `POST /api/v1/admin/api-keys/{id}/revoke`, and the permission key `admin.apikey.manage`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_create_returns_the_secret_exactly_once(admin_client, service_user):
    response = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "website", "user_id": str(service_user.id),
              "scopes": ["inventory.item.read"]},
    )
    assert response.status_code == 201
    assert response.json()["key"].startswith("atk_")

    listed = await admin_client.get("/api/v1/admin/api-keys")
    assert "key" not in listed.json()["items"][0]
    assert "secret_sha256" not in listed.json()["items"][0]


@pytest.mark.asyncio
async def test_scopes_must_exist_in_the_catalog(admin_client, service_user):
    """D-009: a tenant cannot invent a permission key no code checks."""
    response = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "bad", "user_id": str(service_user.id),
              "scopes": ["inventory.item.invented"]},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_revoke_takes_effect_immediately(admin_client, api_key_factory, client):
    full, key = await api_key_factory(scopes=["inventory.item.read"])
    await admin_client.post(f"/api/v1/admin/api-keys/{key.id}/revoke")
    response = await client.get(
        "/api/v1/inventory/items", headers={"Authorization": f"Bearer {full}"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_endpoints_require_the_permission(client_without_permission):
    response = await client_without_permission.get("/api/v1/admin/api-keys")
    assert response.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && ~/.local/bin/uv run pytest tests/modules/admin/test_api_key_endpoints.py -v`
Expected: FAIL — 404, the routes do not exist.

- [ ] **Step 3: Register the permission key**

In `backend/app/core/rbac.py`, beside the existing `ADMIN_*` constants (`rbac.py:54+`):

```python
ADMIN_APIKEY_MANAGE = "admin.apikey.manage"
```

Register it in the same place and the same way the other `ADMIN_*` keys are registered — follow the
existing registration call, do not invent a second mechanism.

- [ ] **Step 4: Implement the endpoints**

Follow the admin module's existing anatomy exactly (`schemas/`, `service/`, `router.py`). Three
routes, all behind `require_permission(ADMIN_APIKEY_MANAGE)`:

- `POST /api/v1/admin/api-keys` → validate every requested scope against `rbac.catalog_keys()`
  (422 on an unknown key), `mint_api_key(tenant.slug)`, persist the digest, return the full key
  **once** in the response body.
- `GET /api/v1/admin/api-keys` → list for the tenant. The response schema must not include
  `secret_sha256`; return `prefix`, `name`, `scopes`, `expires_at`, `revoked_at`, `created_at`.
- `POST /api/v1/admin/api-keys/{id}/revoke` → set `revoked_at`; idempotent (revoking twice is 200,
  not an error).

- [ ] **Step 5: Run to verify they pass**

Run: `cd backend && ~/.local/bin/uv run pytest tests/modules/admin/test_api_key_endpoints.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/rbac.py backend/app/modules/admin/ backend/tests/modules/admin/
git commit -m "feat(admin): create, list and revoke API keys

Scopes validate against the RBAC catalog so a tenant cannot grant a key a
permission no code checks (D-009). The secret is returned once on create and
never again."
```

## Task 5: Rate limiting at the edge

**Files:**
- Modify: `frontend/nginx.conf` (the `/api` proxy is at `nginx.conf:13`)
- Test: manual — documented below, no automated test

**Design note.** There is no rate limiting in Atlas today, for human users either. Putting it in
nginx rather than Python keeps it off the request path and out of the query budget. Limits sized
against the market: Cloudbeds allows 5 req/s per property (10 for tech partners); Toast allows
20 req/s burst with 10,000 per 15 minutes, and throttles `GET /menus` to 1 req/s
(https://doc.toasttab.com/doc/devguide/apiRateLimiting.html).

- [ ] **Step 1: Add the zone and limit**

In `frontend/nginx.conf`, at the `http` level:

```nginx
# Rate limit per credential, not per IP: a property's website is one server, so every
# request shares a source address and an IP limit would either throttle the whole
# property or nothing at all. 10 r/s with burst 20 sits between Cloudbeds' 5 r/s per
# property and Toast's 20 r/s burst.
limit_req_zone $http_authorization zone=atlas_api:10m rate=10r/s;
```

And inside the `/api` location (`nginx.conf:13`):

```nginx
    limit_req zone=atlas_api burst=20 nodelay;
    limit_req_status 429;
```

- [ ] **Step 2: Verify the config parses**

```bash
docker compose up -d --build frontend
docker compose exec frontend nginx -t
```
Expected: `syntax is ok` / `test is successful`

- [ ] **Step 3: Verify the limit actually fires**

```bash
for i in $(seq 1 40); do \
  curl -s -o /dev/null -w "%{http_code} " \
    -H "Authorization: Bearer atk_acme_test" http://localhost:5173/api/v1/health; \
done; echo
```
Expected: a run of `200`/`401` responses followed by `429`s once the burst is exhausted.

- [ ] **Step 4: Commit**

```bash
git add frontend/nginx.conf
git commit -m "feat(deploy): rate limit /api per credential at the edge

Keyed on the Authorization header, not the IP: a property's website is one
server, so an IP limit would throttle the whole property or nothing."
```

## Task 6: Document the decision and the operator flow

**Files:**
- Modify: `DECISIONS.md`
- Modify: `docs/api.md`
- Modify: `PROGRESS.md`

- [ ] **Step 1: Record the decision**

Append to `DECISIONS.md` (numbered after the current last entry):

> **D-0XX Bearer credentials now have two shapes.** A request principal can arrive as a user
> access JWT or as a machine API key, and both converge on the same `CurrentUser` inside the one
> principal builder (`core/deps.py`), which is why no router, no `require_permission` call and no
> idempotency path changed. The tenant ref rides inside the key string so the D-007 ContextVar can
> be set before any lookup — keeping the sanctioned `system_context()` bypass list at exactly four
> — and a forged ref finds no row. Secrets are sha256, not argon2: they are CSPRNG output rather
> than guessable passwords, and argon2id at the D-008 parameters costs tens of ms per request.
> Scopes intersect the user's resolved permissions and may only narrow them. Rejected: OAuth2
> client-credentials (Toast's model, but it exists to separate credential from tenant because one
> client serves many restaurants; a property's own website serves one property) and a service user
> on the existing JWT flow (works today with zero code, but the credential is a password on the
> public login endpoint, every login leaks a `core_refresh_sessions` row with no purge job, and
> revocation granularity is the whole user so there is no zero-downtime rotation).

- [ ] **Step 2: Document the operator flow in `docs/api.md`**

Cover: creating a key in Admin, that the secret is shown once, how to send it
(`Authorization: Bearer atk_...`), how scopes narrow it, how to rotate with overlap (create the new
key, deploy it, revoke the old one), and the 429 behaviour.

- [ ] **Step 3: Log it in `PROGRESS.md`** per CLAUDE.md §6, one line.

- [ ] **Step 4: Commit**

```bash
git add DECISIONS.md docs/api.md PROGRESS.md
git commit -m "docs: record the machine-credential decision and operator flow"
```

## Phase 18 done when

- [ ] Full backend suite green (`uv run pytest -q`), including every query-count assertion
- [ ] `uv run ruff check .` clean
- [ ] A key authenticates, is narrowed by its scopes, cannot read another tenant, and dies on
      revoke and on expiry — each covered by a test
- [ ] No new `system_context()` call site (`tenancy.py:49-64` still documents four)
- [ ] No change to any of the 436 `CurrentUserDep` call sites
- [ ] `nginx -t` passes and the limit is observed firing
- [ ] `DECISIONS.md`, `docs/api.md` and `PROGRESS.md` updated

---

# Self-review

**Spec coverage.** Q1's shape list maps to tasks 1–6: model and migration (T1), mint/parse with
sha256 and the tenant-in-key rule (T2), the `get_current_user` branch with the joined query and
scope intersection (T3), three admin endpoints behind a new catalog key (T4), nginx rate limiting
(T5), the DECISIONS entry (T6). Q1's "not taken" list is honoured — no OAuth server, no token
endpoint, no `last_used_at` write, no Python rate limiter, no CORS change. Q2–Q6 are Phase 19/20
scope and are deliberately not planned here.

**Placeholders.** Two steps deliberately instruct the implementer to *check the existing code*
rather than hardcoding an assumption — the JSON column helper in T1 Step 3, and the tenant-slug
resolver in T3 Step 3. Both are flagged inline with what to look for and why. They are not
"figure it out": they exist because inventing a second JSON convention or a second slug resolver
would be the wrong outcome, and the plan cannot know the helper's name without reading a file it
has not read.

**Type consistency.** `mint_api_key` returns `(full_key, secret_sha256)` and `parse_api_key`
returns `(tenant_ref, secret_sha256)` in T2, and T3 consumes them in exactly that order and shape.
`ApiKey.scopes` is `list[str] | None` in T1, is intersected as `frozenset(key.scopes)` under a
`is not None` guard in T3, and is validated against `catalog_keys()` in T4. `CurrentUser` is
constructed in T3 with the four fields it actually declares at `deps.py:58-61`.

**Known gap, stated rather than hidden.** The spec notes `User.password_hash` is NOT NULL
(`models.py:131`), so a dedicated service user must carry a hash of a discarded random secret.
That is a real wart. This plan does not create service users — Task 4 binds a key to a `user_id`
the operator supplies — so the wart is deferred to whoever first creates one, and it should be
handled in Phase 19 when the website integration actually needs a service principal.
