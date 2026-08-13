"""Inspection-lot HTTP behaviour (PLAN 9.1, D-050): list (paginated + filtered), point read, the
accept/reject usage decision + cancel over the wire, idempotency, RBAC (read/manage/decide), tenant
isolation, and the ≤3-query list budget (PERFORMANCE §6).

Driven against a real bearer-token client whose tenant has a seeded OPEN inspection lot (a posted,
flagged goods receipt). The decision endpoints exercise the full event-driven chain (decision +
disposition stock move) through the app's own handler registration.
"""

import uuid
from collections.abc import Callable

from httpx import AsyncClient

from tests.conftest import QueryCounter, assert_query_budget
from tests.modules.quality.conftest import QualityApi, QualityPrincipal


async def test_list_inspection_lots(quality_api: QualityApi) -> None:
    """The seeded OPEN lot appears in the paginated list with its server-derived fields."""
    response = await quality_api.client.get("/api/v1/quality/inspection-lots")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    lot = body["items"][0]
    assert lot["status"] == "OPEN"
    assert lot["source"] == "GOODS_RECEIPT"
    assert lot["lot_number"].startswith("QL")
    assert str(lot["item_id"]) == str(quality_api.setup.item_id)


async def test_list_filters_by_status(quality_api: QualityApi) -> None:
    """The status filter narrows the list; an ACCEPTED filter excludes the OPEN lot."""
    open_resp = await quality_api.client.get(
        "/api/v1/quality/inspection-lots", params={"status": "OPEN"}
    )
    assert open_resp.status_code == 200
    assert len(open_resp.json()["items"]) == 1
    accepted_resp = await quality_api.client.get(
        "/api/v1/quality/inspection-lots", params={"status": "ACCEPTED"}
    )
    assert accepted_resp.status_code == 200
    assert accepted_resp.json()["items"] == []


async def test_get_inspection_lot(quality_api: QualityApi) -> None:
    response = await quality_api.client.get(
        f"/api/v1/quality/inspection-lots/{quality_api.setup.lot_id}"
    )
    assert response.status_code == 200, response.text
    assert response.json()["id"] == str(quality_api.setup.lot_id)


async def test_get_unknown_lot_404(quality_api: QualityApi) -> None:
    response = await quality_api.client.get(
        f"/api/v1/quality/inspection-lots/{uuid.uuid4()}"
    )
    assert response.status_code == 404


async def test_decide_accept_over_the_wire(quality_api: QualityApi) -> None:
    """POST /decide with an ACCEPT marks the lot ACCEPTED."""
    setup = quality_api.setup
    response = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json={"accepted_quantity": str(setup.lot_quantity), "rejected_quantity": "0"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ACCEPTED"


async def test_decide_persists_notes(quality_api: QualityApi) -> None:
    """Regression (#161): the optional decision ``notes`` round-trips through decide — persisted
    on the lot, not silently dropped."""
    setup = quality_api.setup
    response = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json={
            "accepted_quantity": str(setup.lot_quantity),
            "rejected_quantity": "0",
            "notes": "visual check passed",
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text
    assert response.json()["notes"] == "visual check passed"
    # A fresh read proves the notes landed in the database, not just the response object.
    read = await quality_api.client.get(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}"
    )
    assert read.status_code == 200
    assert read.json()["notes"] == "visual check passed"


async def test_decide_reject_scrap_over_the_wire(quality_api: QualityApi) -> None:
    """POST /decide with a SCRAP rejection marks the lot REJECTED with the disposition recorded."""
    setup = quality_api.setup
    response = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json={
            "accepted_quantity": "0",
            "rejected_quantity": str(setup.lot_quantity),
            "disposition": "SCRAP",
        },
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "REJECTED"
    assert body["disposition"] == "SCRAP"


async def test_decide_split_mismatch_422(quality_api: QualityApi) -> None:
    setup = quality_api.setup
    response = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json={"accepted_quantity": "1", "rejected_quantity": "1"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "quality.decision_quantity_mismatch"


async def test_decide_is_idempotent(quality_api: QualityApi) -> None:
    """Replaying the decide with the same Idempotency-Key returns the captured response and does not
    re-decide (D-013)."""
    setup = quality_api.setup
    key = uuid.uuid4().hex
    body = {"accepted_quantity": str(setup.lot_quantity), "rejected_quantity": "0"}
    first = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json=body,
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 200, first.text
    replay = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json=body,
        headers={"Idempotency-Key": key},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "ACCEPTED"


async def test_cancel_open_lot_over_the_wire(quality_api: QualityApi) -> None:
    setup = quality_api.setup
    response = await quality_api.client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/cancel"
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "CANCELLED"


# --- RBAC ---------------------------------------------------------------------


async def test_read_requires_permission(
    client: AsyncClient,
    quality_user_factory: Callable[..., object],
) -> None:
    """A principal without quality.inspection.read cannot list lots (403)."""
    principal: QualityPrincipal = await quality_user_factory(keys=())
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await client.get("/api/v1/quality/inspection-lots")
    assert response.status_code == 403


async def test_decide_requires_decide_permission(
    client: AsyncClient,
    db_session,
    quality_user_factory: Callable[..., object],
) -> None:
    """A principal with read+manage but NOT decide cannot decide a lot (403); the distinct authority
    (D-050)."""
    from tests.modules.quality.factories import build_inspection_lot_setup

    principal: QualityPrincipal = await quality_user_factory(
        keys=("quality.inspection.read", "quality.inspection.manage")
    )
    setup = await build_inspection_lot_setup(db_session, principal.tenant_id)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/decide",
        json={"accepted_quantity": str(setup.lot_quantity), "rejected_quantity": "0"},
        headers={"Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 403


async def test_cancel_requires_manage_permission(
    client: AsyncClient,
    db_session,
    quality_user_factory: Callable[..., object],
) -> None:
    """A read-only principal cannot cancel a lot (403)."""
    from tests.modules.quality.factories import build_inspection_lot_setup

    principal: QualityPrincipal = await quality_user_factory(
        keys=("quality.inspection.read",)
    )
    setup = await build_inspection_lot_setup(db_session, principal.tenant_id)
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    response = await client.post(
        f"/api/v1/quality/inspection-lots/{setup.lot_id}/cancel"
    )
    assert response.status_code == 403


# --- Tenant isolation ---------------------------------------------------------


async def test_tenant_isolation(
    quality_api: QualityApi, quality_client_b: AsyncClient
) -> None:
    """Tenant B cannot see (or read) tenant A's inspection lot."""
    lot_id = quality_api.setup.lot_id
    list_resp = await quality_client_b.get("/api/v1/quality/inspection-lots")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"] == []
    get_resp = await quality_client_b.get(f"/api/v1/quality/inspection-lots/{lot_id}")
    assert get_resp.status_code == 404


# --- Performance --------------------------------------------------------------


async def test_list_query_budget(
    quality_api: QualityApi,
    query_counter: Callable[[], QueryCounter],
) -> None:
    """The list endpoint stays within the ≤3-query budget (PERFORMANCE §6)."""
    await assert_query_budget(
        quality_api.client,
        query_counter,
        "/api/v1/quality/inspection-lots",
        budget=3,
    )
