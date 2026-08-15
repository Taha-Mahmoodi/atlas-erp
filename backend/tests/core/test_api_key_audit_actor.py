"""Phase 18 / spec Q1 adversarial: does the machine credential keep the D-010 actor
RESOLVABLE, and can an operator tell a website's write from a human's?

Q1's whole argument for binding a key to a real ``core_users`` row (rather than minting a
synthetic principal id) is that ``AuditLog.actor_user_id`` is nullable with NO foreign key
and the 13 ``submitted_by``/``approver_id``/``approved_by``/``decision_by`` columns across
the modules deliberately never hard-FK to ``core_users`` either. Nothing in that chain would
reject a dangling id — so "the id resolves" has to be a property of the AUTHENTICATION path,
not of a constraint on the audit table.

These tests attack that property from both ends: the id the key path hands downstream, and
the DB constraint that stops a key ever pointing at a user the request's tenant cannot see.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import API_KEY_PREFIX, mint_api_key
from app.core.jobs import Job
from app.core.models import ApiKey, AuditLog, User
from app.core.rbac import ADMIN_USER_MANAGE
from app.core.tenancy import tenant_context
from app.modules.admin.service import assign_role, create_role
from tests.conftest import ProvisionedUser

_USERS = "/api/v1/admin/users"


def _bearer(full_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {full_key}"}


async def _persist_key(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    scopes: list[str] | None = None,
) -> str:
    """Mint + persist a key the way admin/service.create_api_key does, returning the full
    string. Local to this module so an attack can bind a key to an ARBITRARY user id, which
    the shared api_key_factory (keyed on a ProvisionedUser) cannot express."""
    full, digest = mint_api_key(tenant_id)
    with tenant_context(tenant_id):
        session.add(
            ApiKey(
                user_id=user_id,
                name="website",
                prefix=f"{API_KEY_PREFIX}_{tenant_id.hex}",
                secret_sha256=digest,
                scopes=scopes,
            )
        )
        await session.commit()
    return full


# --- The actor a key stamps must be a LIVE user row ---------------------------


async def test_key_audit_actor_resolves_to_a_live_user_row(
    client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """The claim under review, tested as a JOIN rather than an equality.

    ``test_key_stamps_the_audit_actor`` asserts the stamped id EQUALS the fixture's user id,
    which would still pass if that id named no row at all. Resolve it the way an operator's
    audit viewer would — actor_user_id -> core_users — and require an active row in the audit
    row's OWN tenant.
    """
    full = await _persist_key(
        db_session,
        admin_user.tenant_id,
        admin_user.user_id,
        scopes=[ADMIN_USER_MANAGE],
    )

    response = await client.post(
        _USERS,
        headers=_bearer(full),
        json={"email": "kiosk@acme.test", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text

    with tenant_context(admin_user.tenant_id):
        row = (
            await db_session.execute(
                select(AuditLog.actor_user_id, AuditLog.tenant_id, User.email, User.is_active)
                .join(User, User.id == AuditLog.actor_user_id)
                .where(
                    AuditLog.entity_table == "core_users",
                    AuditLog.entity_id == response.json()["id"],
                )
            )
        ).one_or_none()

    assert row is not None, "actor_user_id did not resolve to any core_users row"
    actor_id, audit_tenant_id, email, is_active = row
    assert actor_id == admin_user.user_id
    assert email == admin_user.email
    assert is_active is True
    assert audit_tenant_id == admin_user.tenant_id


async def test_key_bound_to_a_foreign_tenants_user_cannot_be_persisted(
    db_session: AsyncSession,
    admin_user: ProvisionedUser,
    user_factory,
) -> None:
    """The forgery that would make the actor unresolvable-in-context: a key row in tenant A
    naming a user of tenant B. Authentication joins User to ApiKey under the D-007 filter, so
    such a key would resolve to nothing — but the row must not exist in the first place, and
    the (tenant_id, user_id) composite FK from tenant_fk() is what stops it. Portable: the
    SQLite FK pragma is attached by build_engine (D-003/D-007 item 4).
    """
    other = await user_factory(slug="beta", email="owner@beta.test")

    with pytest.raises(IntegrityError):
        await _persist_key(
            db_session,
            admin_user.tenant_id,
            other.user_id,  # tenant B's user, tenant A's key
        )
    await db_session.rollback()


async def test_key_bound_to_a_nonexistent_user_cannot_be_persisted(
    db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """Same backstop against a random id: no user row, no key row, so no audit row can ever
    carry a dangling actor sourced from a key."""
    with pytest.raises(IntegrityError):
        await _persist_key(
            db_session, admin_user.tenant_id, uuid.uuid4()
        )
    await db_session.rollback()


async def test_key_of_a_deactivated_user_writes_nothing(
    client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """A deactivated user is still a resolvable row, but its key must stop working — an
    actor that resolves to ``is_active=False`` would let a decommissioned principal keep
    signing writes. deps.py checks is_active on the key path; assert it leaves NO new audit
    rows behind, not merely a 401."""
    full = await _persist_key(
        db_session,
        admin_user.tenant_id,
        admin_user.user_id,
        scopes=[ADMIN_USER_MANAGE],
    )
    with tenant_context(admin_user.tenant_id):
        user = (
            await db_session.execute(select(User).where(User.id == admin_user.user_id))
        ).scalar_one()
        user.is_active = False
        await db_session.commit()
        before = len(
            (await db_session.execute(select(AuditLog.id))).scalars().all()
        )

    response = await client.post(
        _USERS,
        headers=_bearer(full),
        json={"email": "kiosk@acme.test", "password": "correct-horse-battery"},
    )
    assert response.status_code == 401, response.text

    with tenant_context(admin_user.tenant_id):
        after = len((await db_session.execute(select(AuditLog.id))).scalars().all())
    assert after == before


# --- The 13 submitted_by / approver_id sites ----------------------------------


async def test_key_stamps_a_resolvable_submitted_by_on_a_document(
    client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """One of the 13 sites, end to end: ``core_jobs.submitted_by_user_id`` is a bare
    ``sa.Uuid`` with no FK, written from ``current.user_id``. An MRP run is the cheapest of
    the thirteen to reach (no document prerequisites), and it is a real write through a
    module router, not a core one — so it exercises the same CurrentUser every other
    ``submitted_by``/``approver_id`` site reads.
    """
    with tenant_context(admin_user.tenant_id):
        role = await create_role(
            db_session, admin_user.tenant_id, "MRP", ["manufacturing.mrp.run"]
        )
        await assign_role(
            db_session, admin_user.tenant_id, admin_user.user_id, role.id, token_version=0
        )
        await db_session.commit()

    full = await _persist_key(
        db_session,
        admin_user.tenant_id,
        admin_user.user_id,
        scopes=["manufacturing.mrp.run"],
    )

    response = await client.post(
        "/api/v1/manufacturing/mrp/runs",
        headers={**_bearer(full), "Idempotency-Key": str(uuid.uuid4())},
        json={},
    )
    assert response.status_code == 202, response.text

    with tenant_context(admin_user.tenant_id):
        row = (
            await db_session.execute(
                select(Job.submitted_by_user_id, User.email)
                .join(User, User.id == Job.submitted_by_user_id)
                .where(Job.id == uuid.UUID(response.json()["job_id"]))
            )
        ).one_or_none()

    assert row is not None, "submitted_by_user_id did not resolve to any core_users row"
    assert row[0] == admin_user.user_id
    assert row[1] == admin_user.email


# --- Issuing a credential is itself a write -----------------------------------


async def test_issuing_a_key_is_audited(
    admin_client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """D-010 has no "except credentials" clause. Minting a key hands a machine the bound
    user's whole permission set — the same escalation ``UserRole`` grants, and UserRole IS
    AuditMixin. Without an audit row, "who issued the credential that made this change" is
    unanswerable from the trail, which is precisely the actor question one hop back."""
    response = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "website", "user_id": str(admin_user.user_id), "scopes": None},
    )
    assert response.status_code == 201, response.text

    with tenant_context(admin_user.tenant_id):
        rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_table == "core_api_keys",
                        AuditLog.entity_id == response.json()["id"],
                    )
                )
            )
            .scalars()
            .all()
        )

    assert [row.action for row in rows] == ["INSERT"]
    assert rows[0].actor_user_id == admin_user.user_id


async def test_key_audit_never_records_the_stored_digest(
    admin_client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """The reason auditing this table is not free: the row carries the secret's digest, and
    the audit viewer is a different permission (``admin.audit.read``) from the one that may
    see keys. An offline dictionary attack on a sha256 digest is cheap-ish for short inputs,
    and D-010 already excludes ``password_hash`` on User for the same reason — so the digest
    belongs in ``__audit_exclude__``, exactly like it."""
    response = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "website", "user_id": str(admin_user.user_id), "scopes": None},
    )
    assert response.status_code == 201, response.text

    with tenant_context(admin_user.tenant_id):
        diffs = (
            (
                await db_session.execute(
                    select(AuditLog.diff).where(AuditLog.entity_table == "core_api_keys")
                )
            )
            .scalars()
            .all()
        )

    assert diffs, "no audit row was written for the key"
    dumped = str(diffs)
    assert "secret_sha256" not in dumped
    # split("_", 2)[2], NOT rsplit("_", 1)[-1]: the key is
    # ``{prefix}_{tenant_hex}_{secret}`` and ``secrets.token_urlsafe`` emits '_', so
    # splitting on the LAST underscore lands INSIDE the secret and leaves a fragment —
    # a single character roughly one run in twenty, which then trivially appears in the
    # audit row's timestamps and failed this assertion for the wrong reason. maxsplit=2
    # is how ``parse_api_key`` itself reads the key (core/auth.py), and the same pitfall
    # is already documented on the minting side (admin/service.py).
    assert response.json()["key"].split("_", 2)[2] not in dumped


async def test_revoking_a_key_is_audited(
    admin_client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """Revocation is the other half of the credential's lifecycle: an operator answering
    "when did the website lose access, and who cut it" needs the actor on the UPDATE too."""
    created = await admin_client.post(
        "/api/v1/admin/api-keys",
        json={"name": "website", "user_id": str(admin_user.user_id), "scopes": None},
    )
    assert created.status_code == 201, created.text
    key_id = created.json()["id"]

    revoked = await admin_client.post(f"/api/v1/admin/api-keys/{key_id}/revoke")
    assert revoked.status_code == 200, revoked.text

    with tenant_context(admin_user.tenant_id):
        rows = (
            (
                await db_session.execute(
                    select(AuditLog).where(
                        AuditLog.entity_table == "core_api_keys",
                        AuditLog.entity_id == key_id,
                    )
                )
            )
            .scalars()
            .all()
        )

    actions = [row.action for row in rows]
    assert actions == ["INSERT", "UPDATE"]
    assert rows[1].actor_user_id == admin_user.user_id
    assert "revoked_at" in rows[1].diff


# --- The harder question: can an operator tell the website from a human? ------


async def test_audit_row_cannot_distinguish_a_key_from_its_human(
    client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """DOCUMENTS A KNOWN LIMIT rather than asserting a fix (see the review note on D-069).

    A key resolves to the SAME CurrentUser as its bound user's JWT, so the two writes leave
    audit rows that differ in nothing an operator can read: same actor_user_id, same
    request_ip (both clients reach nginx the same way), and this build's core_audit_log has
    no ``source`` column — D-010's literal schema named one, PLAN 3.5 dropped it.

    The consequence: if an operator binds the key to a HUMAN's user (which docs/api.md does
    not warn against), the trail attributes the website's writes to that person. The trail is
    only honest when the key is bound to a dedicated service user, which makes
    distinguishability an operator CONVENTION, not an enforced property. Change this test
    when a ``source`` column lands — do not delete it.
    """
    full = await _persist_key(
        db_session,
        admin_user.tenant_id,
        admin_user.user_id,
        scopes=[ADMIN_USER_MANAGE],
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": admin_user.tenant_slug,
            "email": admin_user.email,
            "password": admin_user.password,
        },
    )
    assert login.status_code == 200, login.text

    by_human = await client.post(
        _USERS,
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"email": "human@acme.test", "password": "correct-horse-battery"},
    )
    by_key = await client.post(
        _USERS,
        headers=_bearer(full),
        json={"email": "website@acme.test", "password": "correct-horse-battery"},
    )
    assert by_human.status_code == 201, by_human.text
    assert by_key.status_code == 201, by_key.text

    with tenant_context(admin_user.tenant_id):
        rows = {
            entity_id: (actor, ip)
            for entity_id, actor, ip in (
                await db_session.execute(
                    select(AuditLog.entity_id, AuditLog.actor_user_id, AuditLog.request_ip).where(
                        AuditLog.entity_table == "core_users",
                        AuditLog.entity_id.in_(
                            [by_human.json()["id"], by_key.json()["id"]]
                        ),
                    )
                )
            ).all()
        }

    assert len(rows) == 2
    assert rows[by_human.json()["id"]] == rows[by_key.json()["id"]], (
        "audit rows now differ between credential shapes — if a source marker was added, "
        "assert it here instead of deleting this test"
    )
    # And no column anywhere carries the credential shape.
    assert "source" not in {column.key for column in AuditLog.__table__.columns}


async def test_key_expiry_boundary_leaves_no_actor(
    client: AsyncClient, db_session: AsyncSession, admin_user: ProvisionedUser
) -> None:
    """``expires_at <= now`` is inclusive in deps.py; a key expiring exactly now must not
    author a write. Guards the boundary the existing expiry test (one second in the past)
    steps over."""
    full, digest = mint_api_key(admin_user.tenant_id)
    with tenant_context(admin_user.tenant_id):
        db_session.add(
            ApiKey(
                user_id=admin_user.user_id,
                name="website",
                prefix=f"{API_KEY_PREFIX}_{admin_user.tenant_id.hex}",
                secret_sha256=digest,
                scopes=[ADMIN_USER_MANAGE],
                expires_at=datetime.now(UTC),
            )
        )
        await db_session.commit()

    response = await client.post(
        _USERS,
        headers=_bearer(full),
        json={"email": "kiosk@acme.test", "password": "correct-horse-battery"},
    )
    assert response.status_code == 401, response.text
