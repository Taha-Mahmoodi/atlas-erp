"""Core-level document-flow read endpoint (D-012).

JUSTIFIED ADDITION to core (same precedent as core/security_router.py / D-027): the document
registry is a cross-cutting platform concern owned by no business module — STRUCTURE's module
list has no `docflow` package — so its read API lives in core/ as a deliberate, recorded
exception (recorded in DECISIONS.md alongside D-027). The DocFlowViewer renders the chain the
endpoint returns. Logic stays thin: it calls core/docflow.get_document_chain and serializes.

Path: GET /api/v1/documents/{document_id}/chain (the binding PLAN-task path; D-012's draft
named /api/v1/core/documents/{id}/flow — deviation noted in DECISIONS.md, the chain shape is
identical). Guarded by get_current_user only (the task spec): any authenticated user may view
their tenant's document flow; finer per-doc-type gating (the seeded core.document.read key) is
a later module concern. Tenant-scoped via the D-007 ORM filter — get_current_user set the
tenant context, so a chain query can never return another tenant's documents.
"""

import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUserDep, SessionDep
from app.core.docflow import get_document_chain
from app.core.exceptions import NotFoundError
from app.core.schemas import DocChainEdge, DocChainNode, DocChainResponse

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


@router.get("/{document_id}/chain", response_model=DocChainResponse)
async def read_document_chain(
    document_id: uuid.UUID,
    current: CurrentUserDep,
    session: SessionDep,
) -> DocChainResponse:
    """Return the full bidirectional flow chain (nodes + edges) for one document. 404 when
    the id is unknown to this tenant (an empty chain — get_document_chain returns no nodes for
    an id that is not a registry row in the caller's tenant scope)."""
    chain = await get_document_chain(session, current.tenant_id, document_id)
    if not chain.nodes:
        raise NotFoundError(
            message="Document not found", code="core.document_not_found"
        )
    return DocChainResponse(
        nodes=[
            DocChainNode(
                document_id=node.document_id,
                doc_type=node.doc_type,
                doc_id=node.doc_id,
                doc_number=node.doc_number,
                status=node.status,
            )
            for node in chain.nodes
        ],
        edges=[
            DocChainEdge(
                predecessor_document_id=edge.predecessor_document_id,
                successor_document_id=edge.successor_document_id,
                link_type=edge.link_type,
            )
            for edge in chain.edges
        ],
    )
