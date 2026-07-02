"""PLAN 14.3: the read-only per-tenant number-sequence viewer (D-012). Proves the viewer
lists the tenant's sequences, is tenant-isolated, is guarded by admin.numbering.read, and
runs within the PERFORMANCE §2 query budget. Sequences are seeded through the real
core/numbering.ensure_sequence path (D-025: factories go through real services).
"""

from app.core.numbering import ensure_sequence
from app.core.tenancy import system_context
from tests.conftest import assert_query_budget

_ADMIN = "/api/v1/admin"


async def _seed_sequence(db_session, tenant_id, name, prefix):
    with system_context():
        await ensure_sequence(
            db_session, tenant_id, name=name, prefix=prefix, padding=5, year_reset=False
        )
        await db_session.commit()


async def test_number_sequences_viewer_lists(admin_client, admin_user, db_session):
    await _seed_sequence(db_session, admin_user.tenant_id, "finance.invoice", "INV")
    resp = await admin_client.get(f"{_ADMIN}/number-sequences")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    row = next(r for r in items if r["name"] == "finance.invoice")
    assert row["prefix"] == "INV"
    assert row["padding"] == 5
    assert row["next_value"] == 1
    assert row["year_reset"] is False


async def test_number_sequences_are_tenant_isolated(
    admin_client, admin_user, db_session, tenant_b
):
    await _seed_sequence(db_session, admin_user.tenant_id, "finance.invoice", "INV")
    await _seed_sequence(db_session, tenant_b, "finance.order", "SO")
    resp = await admin_client.get(f"{_ADMIN}/number-sequences")
    names = {row["name"] for row in resp.json()["items"]}
    assert "finance.invoice" in names
    assert "finance.order" not in names  # tenant_b's sequence is invisible


async def test_number_sequences_require_permission(authed_client):
    resp = await authed_client.get(f"{_ADMIN}/number-sequences")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "rbac.permission_denied"


async def test_number_sequences_query_budget(
    admin_client, admin_user, db_session, query_counter
):
    await _seed_sequence(db_session, admin_user.tenant_id, "finance.invoice", "INV")
    await assert_query_budget(admin_client, query_counter, f"{_ADMIN}/number-sequences")
