"""D-012 document registry, flow links, and bidirectional chain traversal, proven against
the real session/db on the migrated template (D-025).

Covers: register_document creates a unique registry row per (doc_type, doc_id); link_documents
creates an edge and rejects a duplicate; get_document_chain returns the full chain across a 4-
document P2P flow from a MIDDLE node in BOTH directions; a diamond (shared predecessor)
terminates without looping; the partial unique index allows many NULL doc_numbers but rejects
two equal numbers in one tenant while letting different tenants share a number; chain queries
are tenant-isolated; and GET /api/v1/documents/{id}/chain returns the chain for an authed user
and 404 for an unknown id.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import (
    Document,
    get_document_chain,
    link_documents,
    register_document,
)
from app.core.tenancy import tenant_context
from tests.conftest import ProvisionedUser

DocumentFactory = Callable[..., Awaitable[Document]]
LinkFactory = Callable[..., Awaitable[None]]


# --- register_document --------------------------------------------------------


async def test_register_document_creates_a_registry_row(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_document: DocumentFactory
) -> None:
    doc = await make_document(tenant_a, "sales.order", status="DRAFT")

    assert doc.tenant_id == tenant_a
    assert doc.doc_type == "sales.order"
    assert doc.doc_number is None
    assert doc.status == "DRAFT"


async def test_register_document_rejects_duplicate_doc_type_and_doc_id(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    business_row_id = uuid.uuid4()
    with tenant_context(tenant_a):
        await register_document(db_session, tenant_a, "sales.order", business_row_id)
        with pytest.raises(IntegrityError):
            # Same (doc_type, doc_id) twice in one tenant violates the UNIQUE constraint.
            await register_document(db_session, tenant_a, "sales.order", business_row_id)
            await db_session.flush()


# --- link_documents -----------------------------------------------------------


async def test_link_documents_creates_an_edge(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    make_document: DocumentFactory,
    make_link: LinkFactory,
) -> None:
    predecessor = await make_document(tenant_a, "procurement.requisition")
    successor = await make_document(tenant_a, "procurement.purchase_order")

    await make_link(tenant_a, predecessor.id, successor.id, "fulfills")

    chain = await _chain(db_session, tenant_a, predecessor.id)
    assert {e.predecessor_document_id for e in chain.edges} == {predecessor.id}
    assert {e.successor_document_id for e in chain.edges} == {successor.id}
    assert chain.edges[0].link_type == "fulfills"


async def test_duplicate_edge_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_document: DocumentFactory
) -> None:
    predecessor = await make_document(tenant_a, "procurement.requisition")
    successor = await make_document(tenant_a, "procurement.purchase_order")
    with tenant_context(tenant_a):
        await link_documents(db_session, tenant_a, predecessor.id, successor.id, "fulfills")
        with pytest.raises(IntegrityError):
            await link_documents(db_session, tenant_a, predecessor.id, successor.id, "invoices")
            await db_session.flush()


# --- get_document_chain: full chain across 4 docs from a middle node -----------


async def _chain(session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID):  # noqa: ANN202
    with tenant_context(tenant_id):
        return await get_document_chain(session, tenant_id, document_id)


async def test_chain_from_a_middle_node_returns_all_four_in_both_directions(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    make_document: DocumentFactory,
    make_link: LinkFactory,
) -> None:
    # requisition -> PO -> GR -> invoice
    requisition = await make_document(tenant_a, "procurement.requisition")
    purchase_order = await make_document(tenant_a, "procurement.purchase_order")
    goods_receipt = await make_document(tenant_a, "inventory.goods_receipt")
    invoice = await make_document(tenant_a, "finance.ap_invoice")
    await make_link(tenant_a, requisition.id, purchase_order.id, "fulfills")
    await make_link(tenant_a, purchase_order.id, goods_receipt.id, "receives")
    await make_link(tenant_a, goods_receipt.id, invoice.id, "invoices")

    # Query from the PO (a middle node): ancestors (requisition) AND descendants (GR, invoice).
    chain = await _chain(db_session, tenant_a, purchase_order.id)

    node_ids = {n.document_id for n in chain.nodes}
    assert node_ids == {requisition.id, purchase_order.id, goods_receipt.id, invoice.id}
    edge_pairs = {(e.predecessor_document_id, e.successor_document_id) for e in chain.edges}
    assert edge_pairs == {
        (requisition.id, purchase_order.id),
        (purchase_order.id, goods_receipt.id),
        (goods_receipt.id, invoice.id),
    }


async def test_chain_handles_a_diamond_without_infinite_loop(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    make_document: DocumentFactory,
    make_link: LinkFactory,
) -> None:
    # Diamond / shared predecessor: order -> {delivery_one, delivery_two} -> invoice.
    order = await make_document(tenant_a, "sales.order")
    delivery_one = await make_document(tenant_a, "sales.delivery")
    delivery_two = await make_document(tenant_a, "sales.delivery")
    invoice = await make_document(tenant_a, "finance.ar_invoice")
    await make_link(tenant_a, order.id, delivery_one.id)
    await make_link(tenant_a, order.id, delivery_two.id)
    await make_link(tenant_a, delivery_one.id, invoice.id)
    await make_link(tenant_a, delivery_two.id, invoice.id)

    # From the shared predecessor, traversal visits each node once and terminates.
    chain = await _chain(db_session, tenant_a, order.id)

    node_ids = {n.document_id for n in chain.nodes}
    assert node_ids == {order.id, delivery_one.id, delivery_two.id, invoice.id}
    assert len(chain.nodes) == 4  # each node exactly once despite two paths to the invoice
    assert len(chain.edges) == 4


# --- partial unique index on (tenant_id, doc_number) --------------------------


async def test_many_documents_may_have_null_doc_number(
    db_session: AsyncSession, tenant_a: uuid.UUID, make_document: DocumentFactory
) -> None:
    # The partial unique index excludes NULLs, so any number of unnumbered drafts coexist.
    await make_document(tenant_a, "sales.order")
    await make_document(tenant_a, "sales.order")
    await make_document(tenant_a, "sales.order")
    # No IntegrityError: reaching here is the assertion.


async def test_duplicate_doc_number_in_one_tenant_is_rejected(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    with tenant_context(tenant_a):
        await register_document(
            db_session, tenant_a, "finance.ar_invoice", uuid.uuid4(), doc_number="INV-2026-00001"
        )
        with pytest.raises(IntegrityError):
            await register_document(
                db_session,
                tenant_a,
                "finance.ar_invoice",
                uuid.uuid4(),
                doc_number="INV-2026-00001",
            )
            await db_session.flush()


async def test_different_tenants_may_share_a_doc_number(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    make_document: DocumentFactory,
) -> None:
    a_doc = await make_document(tenant_a, "finance.ar_invoice", doc_number="INV-2026-00001")
    b_doc = await make_document(tenant_b, "finance.ar_invoice", doc_number="INV-2026-00001")

    # Same number, different tenants — the partial index is per-tenant, so both persist.
    assert a_doc.doc_number == b_doc.doc_number == "INV-2026-00001"
    assert a_doc.tenant_id != b_doc.tenant_id


# --- tenant isolation of the chain --------------------------------------------


async def test_chain_query_never_returns_another_tenants_documents(
    db_session: AsyncSession,
    tenant_a: uuid.UUID,
    tenant_b: uuid.UUID,
    make_document: DocumentFactory,
    make_link: LinkFactory,
) -> None:
    a_pred = await make_document(tenant_a, "sales.order")
    a_succ = await make_document(tenant_a, "sales.delivery")
    await make_link(tenant_a, a_pred.id, a_succ.id)
    # Tenant B has its own unrelated chain.
    b_pred = await make_document(tenant_b, "sales.order")
    b_succ = await make_document(tenant_b, "sales.delivery")
    await make_link(tenant_b, b_pred.id, b_succ.id)

    # Tenant A's chain query sees only tenant A's documents.
    a_chain = await _chain(db_session, tenant_a, a_pred.id)
    a_ids = {n.document_id for n in a_chain.nodes}
    assert a_ids == {a_pred.id, a_succ.id}
    assert b_pred.id not in a_ids and b_succ.id not in a_ids

    # A query from tenant A for tenant B's document returns an empty chain (filtered out).
    cross = await _chain(db_session, tenant_a, b_pred.id)
    assert cross.nodes == []


# --- the read API endpoint ----------------------------------------------------


async def test_chain_endpoint_returns_the_chain_for_an_authed_user(
    authed_client: AsyncClient,
    provisioned_user: ProvisionedUser,
    db_session: AsyncSession,
    make_document: DocumentFactory,
    make_link: LinkFactory,
) -> None:
    tenant_id = provisioned_user.tenant_id
    order = await make_document(tenant_id, "sales.order", doc_number="SO-0001", status="OPEN")
    delivery = await make_document(tenant_id, "sales.delivery")
    await make_link(tenant_id, order.id, delivery.id, "fulfills")
    # Commit so the app's (separate) request session sees the rows on the shared engine.
    await db_session.commit()

    response = await authed_client.get(f"/api/v1/documents/{order.id}/chain")

    assert response.status_code == 200, response.text
    body = response.json()
    node_ids = {n["document_id"] for n in body["nodes"]}
    assert node_ids == {str(order.id), str(delivery.id)}
    assert len(body["edges"]) == 1
    assert body["edges"][0]["link_type"] == "fulfills"
    order_node = next(n for n in body["nodes"] if n["document_id"] == str(order.id))
    assert order_node["doc_number"] == "SO-0001"
    assert order_node["status"] == "OPEN"


async def test_chain_endpoint_returns_404_for_unknown_id(
    authed_client: AsyncClient,
) -> None:
    response = await authed_client.get(f"/api/v1/documents/{uuid.uuid4()}/chain")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "core.document_not_found"


async def test_chain_endpoint_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/documents/{uuid.uuid4()}/chain")

    assert response.status_code == 401
