"""Core-test fixtures for D-012 numbering + docflow.

Helpers create sequences and registry documents/links through the real core services under
the tenant's own (filtered) context — D-025: factories go through real code, so tenancy
stamping and the FK backstops are exercised by every test that touches data.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.docflow import Document, link_documents, register_document
from app.core.numbering import ensure_sequence
from app.core.tenancy import tenant_context

# A document factory: (tenant_id, doc_type, *, doc_number, status) -> created Document.
DocumentFactory = Callable[..., Awaitable[Document]]


@pytest.fixture
def make_document(db_session: AsyncSession) -> DocumentFactory:
    """Register a document for a tenant via the real core service, under that tenant's
    filtered context. doc_id defaults to a fresh uuid so each call is a distinct business
    row; pass doc_number to exercise the partial unique index."""

    async def _make(
        tenant_id: uuid.UUID,
        doc_type: str = "test.doc",
        *,
        doc_id: uuid.UUID | None = None,
        doc_number: str | None = None,
        status: str | None = None,
    ) -> Document:
        with tenant_context(tenant_id):
            return await register_document(
                db_session,
                tenant_id,
                doc_type,
                doc_id or uuid.uuid4(),
                doc_number=doc_number,
                status=status,
            )

    return _make


@pytest.fixture
def make_link(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    """Create a predecessor -> successor edge via the real core service under the tenant's
    filtered context."""

    async def _make(
        tenant_id: uuid.UUID,
        predecessor: uuid.UUID,
        successor: uuid.UUID,
        link_type: str | None = None,
    ) -> None:
        with tenant_context(tenant_id):
            await link_documents(db_session, tenant_id, predecessor, successor, link_type)

    return _make


@pytest.fixture
def make_sequence(db_session: AsyncSession) -> Callable[..., Awaitable[None]]:
    """Create a number sequence for a tenant via the idempotent real creator under the
    tenant's filtered context."""

    async def _make(
        tenant_id: uuid.UUID,
        name: str = "test.invoice",
        prefix: str = "INV",
        padding: int = 5,
        year_reset: bool = True,
    ) -> None:
        with tenant_context(tenant_id):
            await ensure_sequence(db_session, tenant_id, name, prefix, padding, year_reset)
            await db_session.commit()

    return _make
