"""Machine credential (Phase 18 / spec Q1): the ApiKey row itself.

The model mirrors RefreshSession — hashed secret, revocation, expiry — and is an ordinary
TenantMixin model, so it is read and written through the D-007 filter with no bypass.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import ApiKey
from app.core.tenancy import tenant_context
from tests.conftest import ProvisionedUser


async def test_api_key_row_round_trips(
    db_session: AsyncSession, provisioned_user: ProvisionedUser
) -> None:
    """The model persists and reads back under the ordinary tenant filter (D-007)."""
    with tenant_context(provisioned_user.tenant_id):
        db_session.add(
            ApiKey(
                user_id=provisioned_user.user_id,
                name="website",
                prefix="atk_abc123",
                secret_sha256="0" * 64,
                scopes=["inventory.item.read"],
                expires_at=datetime.now(UTC) + timedelta(days=365),
            )
        )
        await db_session.flush()

        found = (await db_session.execute(select(ApiKey))).scalar_one()

    assert found.tenant_id == provisioned_user.tenant_id
    assert found.name == "website"
    assert found.scopes == ["inventory.item.read"]
    assert found.revoked_at is None
