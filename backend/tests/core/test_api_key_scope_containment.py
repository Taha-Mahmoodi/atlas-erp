"""Adversarial: SCOPE CONTAINMENT for the Phase 18 machine credential (spec Q1, D-009).

The invariant under attack: *a key can only ever narrow its bound user, never widen*. The
observation point is ``GET /api/v1/auth/me``, which serializes ``current.permissions`` —
the exact frozenset ``require_permission`` and the D-009 masking serializer read — so these
tests assert the effective set itself, not a single route's status code.

Keys are planted directly (``_plant_key``) as well as minted over the API on purpose: the
mint-time catalog check is defence in depth, and the row is what authentication actually
trusts, so every containment property has to hold for a row that never passed validation.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.models import ApiKey
from app.core.rbac import ADMIN_APIKEY_MANAGE, ADMIN_ROLE_MANAGE, ADMIN_USER_MANAGE
from app.core.tenancy import tenant_context
from tests.conftest import ProvisionedUser

_KEYS = "/api/v1/admin/api-keys"
_ME = "/api/v1/auth/me"
# A real catalog key (150 of them) that the Administrator role does NOT carry.
_FOREIGN_MODULE_KEY = "finance.journal.post"

PlantKey = Callable[..., Awaitable[str]]


@pytest.fixture
def plant_key(db_session: AsyncSession) -> PlantKey:
    """Persist an ApiKey row directly and hand back the full key string.

    Deliberately bypasses ``admin.service.create_api_key``: authentication trusts the ROW,
    so containment must hold for scopes that never met the mint-time catalog check.
    """

    async def _make(
        principal: ProvisionedUser, *, scopes: list[str] | None = None
    ) -> str:
        full, digest = mint_api_key(principal.tenant_id)
        with tenant_context(principal.tenant_id):
            db_session.add(
                ApiKey(
                    user_id=principal.user_id,
                    name="planted",
                    prefix=f"{API_KEY_PREFIX}_{principal.tenant_id.hex}",
                    secret_sha256=digest,
                    scopes=scopes,
                )
            )
            await db_session.commit()
        return full

    return _make


def _bearer(full_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {full_key}"}


async def _permissions(client: AsyncClient, full_key: str) -> set[str]:
    response = await client.get(_ME, headers=_bearer(full_key))
    assert response.status_code == 200, response.text
    return set(response.json()["permissions"])


# --- The empty list: nothing, or accidentally everything? ---------------------


async def test_empty_scopes_grant_nothing(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """``scopes: []`` is a NARROWING to the empty set, not a falsy "unset" that inherits.

    The distinction is one ``is not None`` in core/deps.py: rewrite it as ``if key.scopes:``
    and an empty list silently becomes full inheritance of the bound user — here, the whole
    Administrator role.
    """
    full = await plant_key(admin_user, scopes=[])

    assert await _permissions(client, full) == set()
    denied = await client.get("/api/v1/admin/users", headers=_bearer(full))
    assert denied.status_code == 403, denied.text


async def test_empty_scopes_survive_the_create_endpoint(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """End to end: ``[]`` must not collapse to NULL through Pydantic or the JSON column.

    ``create_api_key`` writes ``payload.scopes`` (and validates ``payload.scopes or ()``),
    so a falsy-coercion anywhere on that path turns the most restrictive key an operator
    can ask for into the most permissive one.
    """
    created = await admin_client.post(
        _KEYS,
        json={"name": "empty", "user_id": str(admin_user.user_id), "scopes": []},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["scopes"] == [], body

    assert await _permissions(admin_client, body["key"]) == set()


async def test_null_scopes_inherit_and_are_distinguishable_from_empty(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """NULL means inherit unnarrowed (D-069) — and must round-trip as NULL, not as ``[]``.

    Pinned as a pair with the test above: the two values have opposite meanings, so a JSON
    column that conflated them would be a silent full-privilege bug in one direction and a
    silent lockout in the other.
    """
    inherited = await plant_key(admin_user, scopes=None)
    narrowed = await plant_key(admin_user, scopes=[])

    assert ADMIN_USER_MANAGE in await _permissions(client, inherited)
    assert await _permissions(client, narrowed) == set()


# --- Scopes that name something the user does not have -----------------------


async def test_scopes_cannot_add_a_permission_the_user_lacks(
    client: AsyncClient, provisioned_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """A roleless user's key, scoped to real catalog keys, resolves to the empty set."""
    full = await plant_key(
        provisioned_user, scopes=[ADMIN_USER_MANAGE, _FOREIGN_MODULE_KEY]
    )

    assert await _permissions(client, full) == set()


async def test_a_scope_for_a_module_the_user_cannot_touch_is_dropped(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """Mixed scopes: the ones the user holds survive, the foreign-module one is dropped.

    Asserting the exact set (not just a 403 on one route) is what catches a union bug that
    happens to leave the guarded route's own key in place.
    """
    full = await plant_key(admin_user, scopes=[ADMIN_USER_MANAGE, _FOREIGN_MODULE_KEY])

    assert await _permissions(client, full) == {ADMIN_USER_MANAGE}


@pytest.mark.parametrize(
    "scope",
    [
        "ADMIN.USER.MANAGE",
        "Admin.User.Manage",
        " admin.user.manage",
        "admin.user.manage ",
        "admin.user.manage\n",
        "admin.user.manage\t",
        "admin.user.mangae",
        "admin.user.*",
        "*",
    ],
)
async def test_lookalike_scopes_are_rejected_at_mint(
    admin_client: AsyncClient, admin_user: ProvisionedUser, scope: str
) -> None:
    """Catalog membership is exact string equality — no casefold, no strip, no globbing.

    ``*`` and ``admin.user.*`` are in here because a wildcard convention is the classic way
    a scope system grows a widening path; there is none, and this pins that.
    """
    response = await admin_client.post(
        _KEYS,
        json={"name": "bad", "user_id": str(admin_user.user_id), "scopes": [scope]},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "rbac.unknown_permission"


@pytest.mark.parametrize("scope", ["ADMIN.USER.MANAGE", " admin.user.manage", "*", ""])
async def test_lookalike_scopes_planted_directly_grant_nothing(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey, scope: str
) -> None:
    """Second line: even a row that never passed the mint check fails CLOSED at auth.

    ``frozenset(scopes) & permissions`` is set intersection, so an uncatalogued or
    lookalike string simply matches nothing — the containment does not depend on the
    create endpoint having validated it.
    """
    full = await plant_key(admin_user, scopes=[scope])

    assert await _permissions(client, full) == set()


async def test_a_scope_string_that_is_not_a_list_fails_closed(
    client: AsyncClient, admin_user: ProvisionedUser, db_session: AsyncSession
) -> None:
    """The JSON column will happily hold a bare string; ``frozenset("admin...")`` is then a
    set of CHARACTERS. Assert that degenerate row grants nothing rather than something."""
    full, digest = mint_api_key(admin_user.tenant_id)
    with tenant_context(admin_user.tenant_id):
        db_session.add(
            ApiKey(
                user_id=admin_user.user_id,
                name="degenerate",
                prefix=f"{API_KEY_PREFIX}_{admin_user.tenant_id.hex}",
                secret_sha256=digest,
                scopes=ADMIN_USER_MANAGE,  # type: ignore[arg-type]  - deliberately wrong
            )
        )
        await db_session.commit()

    assert await _permissions(client, full) == set()


# --- The 60-second resolve_permissions memo ----------------------------------


async def test_a_narrow_key_does_not_poison_the_cached_user_resolution(
    client: AsyncClient,
    admin_client: AsyncClient,
    admin_user: ProvisionedUser,
    plant_key: PlantKey,
) -> None:
    """The intersection must not mutate the cached frozenset shared with the JWT path.

    ``resolve_permissions`` hands back the very object stored in ``rbac._CACHE``. If that
    object were a mutable ``set``, ``permissions &= frozenset(key.scopes)`` would narrow it
    IN PLACE and every JWT request by the same user would silently lose permissions for the
    rest of the 60s TTL. Both orders, so the poisoning cannot hide behind cache warm-up.
    """
    narrow = await plant_key(admin_user, scopes=[ADMIN_USER_MANAGE])

    before = set((await admin_client.get(_ME)).json()["permissions"])
    assert await _permissions(client, narrow) == {ADMIN_USER_MANAGE}
    after = set((await admin_client.get(_ME)).json()["permissions"])

    assert after == before
    assert ADMIN_ROLE_MANAGE in after


async def test_two_keys_on_one_user_keep_separate_scopes_across_the_cache(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """The memo is keyed on (tenant, user, token_version) — NOT on the key — so both keys
    hit the same cache entry. Interleaved, each must still see only its own scopes."""
    users_key = await plant_key(admin_user, scopes=[ADMIN_USER_MANAGE])
    roles_key = await plant_key(admin_user, scopes=[ADMIN_ROLE_MANAGE])

    assert await _permissions(client, users_key) == {ADMIN_USER_MANAGE}
    assert await _permissions(client, roles_key) == {ADMIN_ROLE_MANAGE}
    assert await _permissions(client, users_key) == {ADMIN_USER_MANAGE}


async def test_revocation_beats_the_cache_window(
    client: AsyncClient, admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """Revoke inside the 60s memo window: the next request must 401, not ride the cache.

    Safe because the memo holds the USER's resolution only; ``revoked_at`` is re-read from
    the key row on every request. Pinned so a future "cache the key row too" optimisation
    cannot quietly reintroduce a 60-second window on a revoked credential.
    """
    created = await admin_client.post(
        _KEYS,
        json={
            "name": "website",
            "user_id": str(admin_user.user_id),
            "scopes": [ADMIN_USER_MANAGE],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()

    assert await _permissions(client, body["key"]) == {ADMIN_USER_MANAGE}

    revoked = await admin_client.post(f"{_KEYS}/{body['id']}/revoke")
    assert revoked.status_code == 200, revoked.text

    denied = await client.get(_ME, headers=_bearer(body["key"]))
    assert denied.status_code == 401, denied.text


async def test_an_expiry_that_passes_beats_the_cache_window(
    client: AsyncClient,
    admin_user: ProvisionedUser,
    db_session: AsyncSession,
    plant_key: PlantKey,
) -> None:
    """Same shape for expiry: warm the memo, then age the key out and re-present it."""
    full = await plant_key(admin_user, scopes=[ADMIN_USER_MANAGE])
    assert await _permissions(client, full) == {ADMIN_USER_MANAGE}

    with tenant_context(admin_user.tenant_id):
        key = (await db_session.execute(select(ApiKey))).scalar_one()
        key.expires_at = datetime.now(UTC).replace(year=2000)
        await db_session.commit()

    denied = await client.get(_ME, headers=_bearer(full))
    assert denied.status_code == 401, denied.text


# --- Minting from a key: can a scoped credential widen itself? ---------------


async def test_a_scoped_key_cannot_mint_a_key_wider_than_itself(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """The self-widening path: mint is the ONE endpoint that produces a credential whose
    scopes it chooses, so a key scoped to ``admin.apikey.manage`` could otherwise issue
    itself a NULL-scoped key on the same user and walk out with the user's whole set.

    Role assignment cannot do this — it moves the USER's permissions, and the presenting
    key's scopes still narrow the result — which is why D-069's "already possible through
    admin.user.manage" argument does not cover it.
    """
    narrow = await plant_key(admin_user, scopes=[ADMIN_APIKEY_MANAGE])

    escalated = await client.post(
        _KEYS,
        headers=_bearer(narrow),
        json={"name": "escalated", "user_id": str(admin_user.user_id), "scopes": None},
    )
    assert escalated.status_code == 403, escalated.text


async def test_a_scoped_key_can_mint_within_its_own_scopes(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """The containment must not become a lockout: rotating a key at or below the
    presenting key's own scopes is the ordinary operator flow and stays allowed."""
    narrow = await plant_key(admin_user, scopes=[ADMIN_APIKEY_MANAGE, ADMIN_USER_MANAGE])

    created = await client.post(
        _KEYS,
        headers=_bearer(narrow),
        json={
            "name": "rotation",
            "user_id": str(admin_user.user_id),
            "scopes": [ADMIN_USER_MANAGE],
        },
    )
    assert created.status_code == 201, created.text
    assert await _permissions(client, created.json()["key"]) == {ADMIN_USER_MANAGE}


async def test_a_jwt_admin_still_mints_unscoped_keys(
    admin_client: AsyncClient, admin_user: ProvisionedUser
) -> None:
    """D-069 is explicit that ``admin.apikey.manage`` is as strong as the tenant's most
    privileged user for a HUMAN holder — that stays true; only key-presented mints are
    contained. Pinned so the fix above cannot drift into re-litigating D-069."""
    created = await admin_client.post(
        _KEYS,
        json={"name": "human", "user_id": str(admin_user.user_id), "scopes": None},
    )
    assert created.status_code == 201, created.text
    assert ADMIN_ROLE_MANAGE in await _permissions(admin_client, created.json()["key"])


async def test_a_scoped_key_cannot_mint_an_explicit_scope_it_lacks(
    client: AsyncClient, admin_user: ProvisionedUser, plant_key: PlantKey
) -> None:
    """The same escalation with EXPLICIT scopes rather than NULL: the presenting key holds
    only ``admin.apikey.manage``, so ``admin.role.manage`` on the new key is out of reach
    even though the bound user has it."""
    narrow = await plant_key(admin_user, scopes=[ADMIN_APIKEY_MANAGE])

    response = await client.post(
        _KEYS,
        headers=_bearer(narrow),
        json={
            "name": "sideways",
            "user_id": str(admin_user.user_id),
            "scopes": [ADMIN_ROLE_MANAGE],
        },
    )
    assert response.status_code == 403, response.text
