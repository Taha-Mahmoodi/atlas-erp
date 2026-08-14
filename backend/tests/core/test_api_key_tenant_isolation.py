"""Adversarial tenant-isolation review of the Phase 18 machine credential (spec Q1).

Everything here attacks ONE property: a key issued to tenant A must never, by any route,
read or write tenant B. `test_api_keys.py` proves the happy path and two obvious
forgeries; this file is the hostile one, and every test names the attack it runs rather
than the behaviour it expects.

The load-bearing claim under review is core/deps.py's: the key's tenant ref sets the D-007
ContextVar BEFORE the key row is read, so the ORDINARY `with_loader_criteria` filter — not
a hand-written where-clause in the auth code — is what rejects every cross-tenant shape.
`test_auth_lookup_is_filtered_by_the_ordinary_d007_predicate` pins that mechanism by
reading the emitted SQL, so a refactor that swapped the filter for a manual
`.where(ApiKey.tenant_id == ...)` fails here even though every 401 below would still pass.

The ref is attacker-controlled and is NOT validated before it becomes the request's tenant
(core/deps.py sets the ContextVar straight from it, by design, to keep the lookup at one
query). That makes "what can a chosen tenant context reach when the credential check then
fails" a live question, not a theoretical one — hence the two stale-context tests at the
end, which assert on the NEXT request rather than on the failed one.
"""

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.models import ApiKey
from app.core.rbac import ADMIN_USER_MANAGE
from app.core.tenancy import _system_context, system_context, tenant_context
from app.modules.admin.models import Tenant
from tests.conftest import ProvisionedUser, QueryCounter

UserFactory = Callable[..., Awaitable[ProvisionedUser]]
KeyFactory = Callable[..., Awaitable[str]]


def _bearer(full_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {full_key}"}


def _ref(tenant_id: uuid.UUID) -> str:
    """The ref segment the CURRENT key format spells a tenant with, taken from the real
    minter rather than hard-coded, so a format change (slug vs UUID) touches one line."""
    return mint_api_key(tenant_id)[0].split("_", 2)[1]


def _secret_half(full_key: str) -> str:
    """The part after `atk_<ref>_` — what an attacker keeps when rewriting the ref."""
    return full_key.split("_", 2)[2]


def _rewrite_ref(full_key: str, tenant_id: uuid.UUID) -> str:
    """The core forgery: keep a genuine secret, relabel it with another tenant's ref."""
    return f"{API_KEY_PREFIX}_{_ref(tenant_id)}_{_secret_half(full_key)}"


@pytest.fixture
def issue_key(db_session: AsyncSession) -> KeyFactory:
    """Persist a real key row for a principal and hand back the full key string.

    `ref_tenant_id` overrides only the SPOKEN half of the key; the row still belongs to
    `principal`'s tenant. That split is what makes the forgery tests meaningful — the
    attacker controls the ref, never the row.
    """

    async def _make(
        principal: ProvisionedUser,
        *,
        scopes: list[str] | None = None,
        ref_tenant_id: uuid.UUID | None = None,
    ) -> str:
        full, digest = mint_api_key(ref_tenant_id or principal.tenant_id)
        with tenant_context(principal.tenant_id):
            db_session.add(
                ApiKey(
                    user_id=principal.user_id,
                    name="website",
                    prefix=full.rsplit("_", 1)[0],
                    secret_sha256=digest,
                    scopes=scopes,
                )
            )
            await db_session.commit()
        return full

    return _make


# --- The mechanism itself -----------------------------------------------------


async def test_auth_lookup_is_filtered_by_the_ordinary_d007_predicate(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    issue_key: KeyFactory,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The auth code must carry NO hand-written tenant predicate — the D-007 loader
    criteria must supply one for BOTH tenant-scoped entities in the lookup.

    Read the SQL the credential lookup actually emits. If `with_loader_criteria` covered
    only the lead entity (`User`) and not the explicitly joined `ApiKey`, the cross-tenant
    401s below would still pass for the WRONG reason: another tenant's key row would be
    readable and only the user-side predicate would be stopping it. That is the difference
    between a defence and a coincidence, and only the SQL shows which one is running.
    """
    full = await issue_key(admin_user, scopes=[ADMIN_USER_MANAGE])

    with query_counter() as qc:
        response = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert response.status_code == 200, response.text

    joined = [s for s in qc.statements if "core_api_keys" in s and "core_users" in s]
    assert len(joined) == 1, "the credential lookup must be ONE joined statement:\n" + "\n".join(
        qc.statements
    )
    lookup = joined[0]
    for table in ("core_api_keys", "core_users"):
        assert _binds_tenant(lookup, table), (
            f"the {table} entity is NOT tenant-filtered by D-007:\n{lookup}"
        )


def _binds_tenant(sql: str, table: str) -> bool:
    """True when `sql` compares `<table>.tenant_id` to a BOUND parameter — the D-007
    predicate. Comparing it to another column instead would tie the two entities together
    without pinning either to the request's tenant, which is a different (weaker) thing."""
    return re.search(rf"{table}\.tenant_id = (\?|%\(\w+\)s|\$\d+|:\w+)", sql) is not None


def test_phase_18_added_no_system_context_bypass() -> None:
    """D-007 sanctions exactly four `system_context()` call sites; this phase added none.

    Asserted on the source of the files the phase put in the auth path — a tree-wide grep
    would count the four pre-existing sites and need editing for unrelated work.
    """
    backend = Path(__file__).resolve().parents[2]
    for relative in ("app/core/deps.py", "app/core/auth.py"):
        assert "system_context()" not in _code_only(backend / relative), relative


def _code_only(path: Path) -> str:
    """Source with comments and docstrings dropped, so prose ABOUT the bypass does not
    read as a call site. Both files document why they need no bypass, at length."""
    lines = [line for line in path.read_text().splitlines() if not line.lstrip().startswith("#")]
    # Docstrings in this codebase are triple-double-quoted; odd-indexed splits are inside one.
    return "".join("\n".join(lines).split('"""')[::2])


# --- Forged and mismatched tenant refs ----------------------------------------


async def test_the_d007_filter_is_the_only_thing_rejecting_a_forged_ref(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """The negative control for this whole file: turn the D-007 filter OFF and the forgery
    below goes through.

    That is the point. `_authenticate_api_key` carries no tenant predicate of its own, so
    with the filter suspended a key whose ref names another tenant authenticates as its own
    tenant. Every 401 in this file therefore comes from the ordinary session filter and
    from nothing else — which is what D-007 requires, and what a hand-written
    `.where(ApiKey.tenant_id == ...)` in the auth code would have quietly replaced.

    NOT a reachable exploit: `_system_context` only ever flips inside `system_context()`,
    which resets it in a `finally`, and each request runs in its own task with its own
    context copy, so no request can inherit a True flag from another. It is forced here
    directly. Worth knowing that RequestIdMiddleware seeds and resets the other five
    request ContextVars but not this one — the containment argument rests entirely on the
    context manager, so any future code that sets the flag without restoring it disarms
    D-007 for the rest of that task.
    """
    victim = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None)
    forged = _rewrite_ref(full, victim.tenant_id)

    assert (await client.get("/api/v1/admin/users", headers=_bearer(forged))).status_code == 401

    token = _system_context.set(True)
    try:
        disarmed = await client.get("/api/v1/admin/users", headers=_bearer(forged))
    finally:
        _system_context.reset(token)

    assert disarmed.status_code == 200, (
        "the forged ref was still rejected with D-007 suspended, so something OTHER than "
        "the session filter is doing the rejecting — find it and delete it"
    )
    # Even disarmed the response is the KEY's own tenant, never the ref's: the admin
    # queries pass an explicit tenant_id taken from CurrentUser, which the auth join set
    # from the user row. Defence in depth, not the defence.
    assert {item["email"] for item in disarmed.json()["items"]} == {admin_user.email}




async def test_key_of_tenant_a_presented_as_tenant_b_cannot_authenticate(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: steal tenant A's key string and rewrite its ref to name tenant B.

    The secret half is genuine and its digest really is in the table; only the ref is a
    lie. The lookup runs under B's context, so A's row is invisible.
    """
    victim = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None)

    honest = await client.get("/api/v1/admin/users", headers=_bearer(full))
    attack = await client.get(
        "/api/v1/admin/users", headers=_bearer(_rewrite_ref(full, victim.tenant_id))
    )

    assert honest.status_code == 200, honest.text
    assert attack.status_code == 401, attack.text


async def test_key_stored_under_a_ref_its_row_does_not_match_is_dead(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: an insider issues a tenant-A row but mints the STRING against tenant B, so
    the credential arrives already claiming B. It must authenticate as nobody — not as B,
    and not as A either."""
    victim = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None, ref_tenant_id=victim.tenant_id)

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert response.status_code == 401, response.text


async def test_unknown_tenant_ref_is_rejected(
    client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Attack: a well-formed ref naming a tenant that does not exist at all."""
    response = await client.get(
        "/api/v1/admin/users", headers=_bearer(f"{API_KEY_PREFIX}_{uuid.uuid4().hex}_anysecret")
    )
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "ref",
    ["", "acme", "ACME", "%", "../acme", "acme'", " acme", "0" * 31, "0" * 33, "zz" * 16],
)
async def test_malformed_tenant_ref_is_rejected(
    client: AsyncClient, admin_user: ProvisionedUser, ref: str
) -> None:
    """Attack: the ref is attacker-controlled free text that becomes the request's tenant.
    Wildcards, quotes, traversal and wrong-length hex must all fail closed — never resolve
    to a real tenant, and never raise (a raise here is a 500, which is an oracle)."""
    response = await client.get(
        "/api/v1/admin/users", headers=_bearer(f"{API_KEY_PREFIX}_{ref}_anysecret")
    )
    assert response.status_code == 401, response.text


# --- A key row whose user belongs to another tenant ---------------------------


async def test_key_cannot_be_stored_against_another_tenants_user(
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
) -> None:
    """Attack: forge the key ROW so `user_id` points at another tenant's user, which would
    make the auth join hand back a foreign principal.

    The D-007 composite FK (tenant_id, user_id) -> core_users(tenant_id, id) is the
    backstop; on SQLite it needs the FK pragma, which build_engine attaches.
    """
    foreign = await user_factory(slug="beta", email="owner@beta.test")
    _, digest = mint_api_key(admin_user.tenant_id)

    with tenant_context(admin_user.tenant_id):
        db_session.add(
            ApiKey(
                user_id=foreign.user_id,  # tenant B's user under tenant A's key
                name="crossed",
                prefix=f"{API_KEY_PREFIX}_{_ref(admin_user.tenant_id)}",
                secret_sha256=digest,
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()
    await db_session.rollback()


async def test_crossed_key_row_forced_past_the_fk_still_cannot_authenticate(
    client: AsyncClient,
    db_engine: AsyncEngine,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
) -> None:
    """Defence in depth: assume the FK is gone (a bad migration, a Postgres deploy that
    never got the constraint) and a crossed row EXISTS. Raw SQL with the pragma off
    writes one.

    The join must still refuse: the loader criteria pins BOTH sides to the ref's tenant,
    so a user row of another tenant cannot satisfy it.
    """
    foreign = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full, digest = mint_api_key(admin_user.tenant_id)

    async with db_engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await conn.execute(
            text(
                "INSERT INTO core_api_keys "
                "(id, tenant_id, user_id, name, prefix, secret_sha256, scopes, "
                " expires_at, revoked_at, created_at, updated_at) "
                "VALUES (:id, :tenant_id, :user_id, 'crossed', :prefix, :digest, NULL, "
                " NULL, NULL, :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(admin_user.tenant_id),
                "user_id": str(foreign.user_id),
                "prefix": f"{API_KEY_PREFIX}_{_ref(admin_user.tenant_id)}",
                "digest": digest,
                "now": datetime.now(UTC).isoformat(sep=" "),
            },
        )

    response = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert response.status_code == 401, response.text


# --- Reaching another tenant's records with a valid key -----------------------


async def test_valid_key_cannot_read_another_tenants_record_by_id(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: authenticate honestly, then ask for a record id belonging to another
    tenant. The ContextVar the key set governs every downstream read."""
    foreign = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None)

    response = await client.get(f"/api/v1/admin/users/{foreign.user_id}", headers=_bearer(full))
    assert response.status_code == 404, response.text


async def test_valid_key_cannot_list_or_revoke_another_tenants_keys(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: use a key to enumerate and then kill the OTHER tenant's credentials."""
    foreign = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    await issue_key(foreign, scopes=None)
    full = await issue_key(admin_user, scopes=None)

    with tenant_context(foreign.tenant_id):
        foreign_key_id = (
            await db_session.execute(select(ApiKey.id).where(ApiKey.user_id == foreign.user_id))
        ).scalar_one()

    listed = await client.get("/api/v1/admin/api-keys", headers=_bearer(full))
    assert listed.status_code == 200, listed.text
    assert str(foreign_key_id) not in {item["id"] for item in listed.json()["items"]}
    assert "secret_sha256" not in listed.text

    revoked = await client.post(
        f"/api/v1/admin/api-keys/{foreign_key_id}/revoke", headers=_bearer(full)
    )
    assert revoked.status_code == 404, revoked.text

    db_session.expire_all()
    with tenant_context(foreign.tenant_id):
        still_live = (
            await db_session.execute(select(ApiKey.revoked_at).where(ApiKey.id == foreign_key_id))
        ).scalar_one()
    assert still_live is None


async def test_key_issued_through_the_api_cannot_bind_another_tenants_user(
    admin_client: AsyncClient,
    user_factory: UserFactory,
) -> None:
    """Attack: POST /api-keys naming a user id from another tenant, which would mint a
    credential authenticating into this tenant while impersonating a foreign row."""
    foreign = await user_factory(slug="beta", email="owner@beta.test", admin=True)

    response = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "website", "user_id": str(foreign.user_id)},
    )
    assert response.status_code == 404, response.text


# --- Deactivated tenant -------------------------------------------------------


async def test_key_for_a_deactivated_tenant_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    issue_key: KeyFactory,
) -> None:
    """Attack: keep using a credential after the tenant is switched off. A JWT dies in
    minutes; a key can live a year, so deactivation has to bite on the next request."""
    full = await issue_key(admin_user, scopes=None)
    before = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert before.status_code == 200, before.text

    await _deactivate(db_session, admin_user.tenant_id)

    after = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert after.status_code == 401, after.text


async def test_deactivating_one_tenant_does_not_disturb_another(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """The other half of the same check: the is_active read must be joined to the KEY's
    tenant, not to whatever tenant row the query happens to reach. If the join were
    missing its ON clause, one deactivation would kill every tenant's keys."""
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    other_key = await issue_key(other, scopes=None)
    await issue_key(admin_user, scopes=None)

    await _deactivate(db_session, admin_user.tenant_id)

    response = await client.get("/api/v1/admin/users", headers=_bearer(other_key))
    assert response.status_code == 200, response.text
    assert {item["email"] for item in response.json()["items"]} == {other.email}


# --- Stale context across requests --------------------------------------------


async def test_back_to_back_keys_from_two_tenants_each_see_only_their_own(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: the SQLAlchemy compiled-statement cache.

    The credential join is a statement shape that only the key path emits, and the D-007
    predicate reaches it through a closure over the ContextVar. If that closure value were
    part of the cache key's baked-in state — the exact failure `track_closure_variables`
    guards, see core/tenancy.py — the FIRST tenant to authenticate with a key would pin its
    id into every later execution of the same shape, and tenant B's key would read tenant
    A's rows. A then B then A again, all succeeding with their OWN data, is what rules it
    out; a single-tenant test cannot.
    """
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    key_a = await issue_key(admin_user, scopes=None)
    key_b = await issue_key(other, scopes=None)

    seen = [
        await _emails_for_key(client, key_a),
        await _emails_for_key(client, key_b),
        await _emails_for_key(client, key_a),
    ]
    assert seen == [{admin_user.email}, {other.email}, {admin_user.email}]


async def test_concurrent_key_requests_do_not_cross_contaminate(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: two tenants' keys in flight at once on one worker. The tenancy ContextVar is
    a process-global; only per-task context copies keep them apart, and `_authenticate_api_key`
    sets it with a bare `.set()` and no reset of its own — it relies entirely on the
    middleware's finally block. Interleave the two and check neither sees the other."""
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    key_a = await issue_key(admin_user, scopes=None)
    key_b = await issue_key(other, scopes=None)

    a, b = await asyncio.gather(
        _emails_for_key(client, key_a), _emails_for_key(client, key_b)
    )
    assert (a, b) == ({admin_user.email}, {other.email})


async def _emails_for_key(client: AsyncClient, full_key: str) -> set[str]:
    listed = await client.get("/api/v1/admin/users", headers=_bearer(full_key))
    assert listed.status_code == 200, listed.text
    return {item["email"] for item in listed.json()["items"]}


async def test_a_failed_key_cannot_inherit_the_previous_requests_tenant(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: warm the ContextVar with a good tenant-A request, then send a key whose ref
    names tenant B but whose secret is A's. If the reset middleware or the ordering inside
    `_authenticate_api_key` were wrong, request 2 would run under A's leftover context and
    the genuine A digest would match."""
    victim = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None)

    warm = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert warm.status_code == 200, warm.text

    response = await client.get(
        "/api/v1/admin/users", headers=_bearer(_rewrite_ref(full, victim.tenant_id))
    )
    assert response.status_code == 401, response.text


async def test_key_request_does_not_leak_its_tenant_into_the_next_request(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
    issue_key: KeyFactory,
) -> None:
    """Attack: a key request for tenant A followed by a JWT request for tenant B. B must
    see B's rows only — the ContextVar must not still hold A."""
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)
    full = await issue_key(admin_user, scopes=None)

    assert (await client.get("/api/v1/admin/users", headers=_bearer(full))).status_code == 200

    assert await _emails_visible_to(client, other) == {other.email}


async def test_failed_key_auth_does_not_leave_a_tenant_context_behind(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    user_factory: UserFactory,
) -> None:
    """Attack: `atk_<victim-ref>_garbage` sets the ContextVar to the victim's tenant and
    THEN fails — the ref is never validated before it becomes the request's tenant. The
    next request on the same worker must not inherit it."""
    other = await user_factory(slug="beta", email="owner@beta.test", admin=True)

    poisoned = await client.get(
        "/api/v1/admin/users",
        headers=_bearer(f"{API_KEY_PREFIX}_{_ref(admin_user.tenant_id)}_garbage"),
    )
    assert poisoned.status_code == 401, poisoned.text

    assert await _emails_visible_to(client, other) == {other.email}


async def _deactivate(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Switch a tenant off the way the admin surface would: mutate the loaded row, not a
    bulk UPDATE — core/audit.py rejects ORM bulk writes against audited models (D-010)."""
    with system_context():
        tenant = await session.get_one(Tenant, tenant_id)
        tenant.is_active = False
        await session.commit()


async def _emails_visible_to(client: AsyncClient, principal: ProvisionedUser) -> set[str]:
    """Log `principal` in with a fresh JWT and list the users it can see."""
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert login.status_code == 200, login.text
    listed = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert listed.status_code == 200, listed.text
    return {item["email"] for item in listed.json()["items"]}
