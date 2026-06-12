"""D-012 document registry, flow links, and chain traversal.

The registry turns the polymorphic (doc_type, doc_id) problem into ordinary FK integrity:
every business document row links to exactly one ``core_documents`` registry entry via the
NOT NULL ``document_id`` FK supplied by ``DocumentMixin``. Predecessor/successor edges live
in ``core_doc_links``, so chain traversal is one generic recursive CTE over two narrow
tables — the ACDOCA-era Document Relationship Browser shape — with zero module-aware code in
core (core imports nothing from modules).

Claim-timing (D-012): a document is registered with ``doc_number`` NULL at creation;
documents with a draft lifecycle are numbered at posting via the numbering claim, documents
permanent at creation are numbered immediately. The partial unique index on
``(tenant_id, doc_number)`` is the DB backstop turning any numbering bug into a constraint
violation.

The ORM models live HERE rather than in core/models.py: models.py is near its ~350-line
soft cap, so the D-012 entities sit in their concern file (consistent with numbering.py and
sanctioned by the PLAN). Noted in DECISIONS.md.
"""

import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.models import (
    Base,
    TenantMixin,
    TimestampMixin,
    UuidPKMixin,
    tenant_fk,
)

# Depth ceiling on chain traversal (D-012): real chains are <10 nodes; the cap plus the
# visited-path cycle guard make a malformed graph terminate instead of spinning.
_MAX_CHAIN_DEPTH = 20


class Document(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """Registry entry for one business document (D-012). ``doc_type`` is a namespaced
    constant (``'sales.order'``, ``'finance.journal_entry'``) declared in module
    constants.py; ``doc_id`` is the PK of the business row in its own table; ``doc_number``
    is assigned at posting (NULL until then); ``status`` is the registry-level status string.

    Not AuditMixin: the registry mirrors business rows that are themselves audited — the
    document's own table carries the audited business state, so auditing the registry too
    would double-record (documented exclusion)."""

    __tablename__ = "core_documents"
    __table_args__ = (
        # One registry row per business document. Explicit name (D-022 convention keys on
        # column 0 only and would collide with tenant_unique()).
        sa.UniqueConstraint(
            "tenant_id", "doc_type", "doc_id", name="uq_core_documents_tenant_id_doc_type_doc_id"
        ),
        # Required so business rows can reference a registry entry via the composite tenant FK
        # (D-007 item 4) — DocumentMixin.document_fk() targets this.
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_documents_tenant_id"),
        # Partial unique index: a tenant may have many UNNUMBERED documents (doc_number NULL)
        # but never two with the SAME doc_number. Both dialect kwargs are required — Postgres
        # and SQLite each need their own (D-012 / D-021 dialect-kwargs pattern); a plain
        # UNIQUE would (incorrectly) reject multiple NULLs on some engines.
        sa.Index(
            "uq_core_documents_tenant_id_doc_number",
            "tenant_id",
            "doc_number",
            unique=True,
            postgresql_where=sa.text("doc_number IS NOT NULL"),
            sqlite_where=sa.text("doc_number IS NOT NULL"),
        ),
        tenant_fk("adm_tenants"),
    )

    doc_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    doc_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    doc_number: Mapped[str | None] = mapped_column(sa.String(60), nullable=True)
    status: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)


class DocumentLink(UuidPKMixin, TenantMixin, TimestampMixin, Base):
    """A predecessor -> successor edge between two registry entries (D-012). ``link_type``
    names the relationship (``'fulfills'``, ``'invoices'``, ``'reverses'``, ``'posts'``).
    Both endpoints carry the composite tenant FK backstop so an edge can never span tenants.
    A CHECK forbids self-edges (a document cannot be its own predecessor)."""

    __tablename__ = "core_doc_links"
    __table_args__ = (
        # One edge per (tenant, predecessor, successor). Explicit name (D-022 column-0 rule).
        sa.UniqueConstraint(
            "tenant_id",
            "predecessor_document_id",
            "successor_document_id",
            name="uq_core_doc_links_tenant_id_predecessor_document_id_successor",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_core_doc_links_tenant_id"),
        # Pass the bare token: the D-022 ck convention wraps it as
        # ck_<table>_<constraint_name> -> ck_core_doc_links_no_self_link (matches 0006).
        sa.CheckConstraint(
            "predecessor_document_id != successor_document_id",
            name="no_self_link",
        ),
        tenant_fk("adm_tenants"),
        # Both endpoints reference core_documents through the composite tenant FK, so the
        # D-022 column-0 convention would name both identically (collision). Spell out
        # distinct names that match migration 0006 exactly.
        sa.ForeignKeyConstraint(
            ["tenant_id", "predecessor_document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_core_doc_links_tenant_id_core_documents",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "successor_document_id"],
            ["core_documents.tenant_id", "core_documents.id"],
            name="fk_core_doc_links_successor_document_id_core_documents",
        ),
    )

    predecessor_document_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    successor_document_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    link_type: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)


def document_fk() -> sa.ForeignKeyConstraint:
    """Composite tenant-safe FK for a business table's ``document_id`` -> core_documents
    (D-007 item 4). A business model that mixes in DocumentMixin adds this to its
    __table_args__ so the link can never point at another tenant's registry row, mirroring
    the tenant_fk()/tenant_unique() pattern in core/models.py."""
    return sa.ForeignKeyConstraint(
        ["tenant_id", "document_id"],
        ["core_documents.tenant_id", "core_documents.id"],
    )


class DocumentMixin:
    """Business-document link mixin (D-012). A business model mixes this in to get a NOT NULL
    ``document_id`` column tying its row to its registry entry — so the row CANNOT be inserted
    without first registering the document (the dual-write discipline D-012 relies on). The
    consuming model must also add ``document_fk()`` to its __table_args__ for the composite
    tenant-safe FK (a mixin cannot inject a multi-column FK into the host's __table_args__,
    exactly as TenantMixin needs the model to add tenant_fk()). UNIQUE so the registry-to-row
    mapping is 1:1.

    Usage in a later module model:

        class SalesOrder(UuidPKMixin, TenantMixin, DocumentMixin, TimestampMixin, Base):
            __tablename__ = "sls_orders"
            __table_args__ = (tenant_unique(), tenant_fk("adm_tenants"), document_fk())
    """

    @declared_attr
    def document_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(sa.Uuid, nullable=False, unique=True)


@dataclass(frozen=True)
class ChainNode:
    """One document in a flow chain — the registry projection the DocFlowViewer renders."""

    document_id: uuid.UUID
    doc_type: str
    doc_id: uuid.UUID
    doc_number: str | None
    status: str | None


@dataclass(frozen=True)
class ChainEdge:
    """One predecessor -> successor edge in a flow chain."""

    predecessor_document_id: uuid.UUID
    successor_document_id: uuid.UUID
    link_type: str | None


@dataclass(frozen=True)
class DocumentChain:
    """Full bidirectional flow chain around a document: every connected node plus every edge
    among them. Usable directly by the read API (nodes + edges for the viewer)."""

    nodes: list[ChainNode]
    edges: list[ChainEdge]


async def register_document(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    doc_type: str,
    doc_id: uuid.UUID,
    *,
    doc_number: str | None = None,
    status: str | None = None,
) -> Document:
    """Insert a registry row for a business document and return it (D-012). Called by the
    creating service in the same transaction as the business-row insert (the DocumentMixin
    NOT NULL FK makes skipping it a hard error). ``doc_number`` is left NULL for draft-
    lifecycle documents (numbered later at posting) and set for documents permanent at
    creation. A Core insert sets tenant_id explicitly — core/docflow is a D-007 sanctioned
    raw-SQL site."""
    document_id = uuid.uuid4()
    await session.execute(
        sa.insert(Document.__table__).values(
            id=document_id,
            tenant_id=tenant_id,
            doc_type=doc_type,
            doc_id=doc_id,
            doc_number=doc_number,
            status=status,
        )
    )
    return (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()


async def link_documents(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    predecessor: uuid.UUID,
    successor: uuid.UUID,
    link_type: str | None = None,
) -> DocumentLink:
    """Create a predecessor -> successor edge and return it (D-012). The UNIQUE(tenant_id,
    predecessor, successor) constraint rejects a duplicate edge as an IntegrityError, and
    the composite tenant FKs reject endpoints from another tenant. A Core insert sets
    tenant_id explicitly (D-007 sanctioned site)."""
    link_id = uuid.uuid4()
    await session.execute(
        sa.insert(DocumentLink.__table__).values(
            id=link_id,
            tenant_id=tenant_id,
            predecessor_document_id=predecessor,
            successor_document_id=successor,
            link_type=link_type,
        )
    )
    return (
        await session.execute(select(DocumentLink).where(DocumentLink.id == link_id))
    ).scalar_one()


def _build_reachability_cte(
    tenant_id: uuid.UUID, start: uuid.UUID, *, forward: bool
) -> sa.sql.Selectable:
    """One recursive CTE collecting every document reachable from ``start`` in ONE direction.

    ``forward=True`` walks successor edges (descendants), ``forward=False`` walks predecessor
    edges (ancestors). The recursive member carries a ``depth`` column capped at
    _MAX_CHAIN_DEPTH and a ``path`` string of visited ids; the join excludes any node already
    on the path, so a diamond or cycle is traversed once and terminates (D-012 visited-path
    guard). Works identically on Postgres and SQLite (both support WITH RECURSIVE).
    """
    links = DocumentLink.__table__
    near = links.c.successor_document_id if forward else links.c.predecessor_document_id
    far = links.c.predecessor_document_id if forward else links.c.successor_document_id

    # Anchor: the start node itself at depth 0. The path representation MUST match how the
    # recursive step casts ids (CAST(<Uuid column> AS VARCHAR)), so the start id is cast the
    # same way — casting a Uuid-typed literal renders dashless hex on SQLite and dashed on
    # PG, exactly as the column cast does, keeping the visited-path guard's LIKE comparison
    # apples-to-apples on both engines (a raw str(start) would carry dashes on SQLite and
    # silently defeat the guard).
    anchor = select(
        sa.literal(start, type_=sa.Uuid).label("document_id"),
        sa.literal(0).label("depth"),
        sa.cast(sa.literal(start, type_=sa.Uuid), sa.String).label("path"),
    ).cte("reach", recursive=True)

    # Recursive step: from each frontier node, follow edges in the chosen direction to the
    # node on the other end, within the tenant, skipping nodes already on the path.
    step = (
        select(
            far.label("document_id"),
            (anchor.c.depth + 1).label("depth"),
            (anchor.c.path + sa.literal(",") + sa.cast(far, sa.String)).label("path"),
        )
        .select_from(anchor.join(links, near == anchor.c.document_id))
        .where(
            links.c.tenant_id == tenant_id,
            anchor.c.depth < _MAX_CHAIN_DEPTH,
            anchor.c.path.notlike(sa.literal("%") + sa.cast(far, sa.String) + sa.literal("%")),
        )
    )
    return anchor.union_all(step)


async def get_document_chain(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> DocumentChain:
    """Traverse the full flow chain around ``document_id`` in BOTH directions and return its
    nodes + edges (D-012). Two recursive CTEs (ancestors via predecessor edges, descendants
    via successor edges) collect every reachable registry id; their union is the connected
    component containing the start node. Edges are the links whose BOTH endpoints fall in that
    set. Cycles and diamonds are handled by the per-CTE visited-path guard, so each node and
    edge appears once. Returns empty nodes/edges when the id is unknown to this tenant.

    Tenant isolation: the CTEs filter links by tenant_id and the registry/edge reads run
    under the caller's tenant context (the D-007 ORM filter), so a chain query never returns
    another tenant's documents.
    """
    ancestors = _build_reachability_cte(tenant_id, document_id, forward=False)
    descendants = _build_reachability_cte(tenant_id, document_id, forward=True)

    ancestor_ids = set(
        (await session.execute(select(ancestors.c.document_id))).scalars().all()
    )
    descendant_ids = set(
        (await session.execute(select(descendants.c.document_id))).scalars().all()
    )
    reachable = ancestor_ids | descendant_ids

    # An unknown id reaches only itself; if it is not a real registry row for this tenant,
    # there are no nodes to return — surface an empty chain (the router maps that to 404).
    document_rows = (
        await session.execute(select(Document).where(Document.id.in_(reachable)))
    ).scalars().all()
    if not document_rows:
        return DocumentChain(nodes=[], edges=[])

    present_ids = {row.id for row in document_rows}
    nodes = [
        ChainNode(
            document_id=row.id,
            doc_type=row.doc_type,
            doc_id=row.doc_id,
            doc_number=row.doc_number,
            status=row.status,
        )
        for row in document_rows
    ]

    link_rows = (
        await session.execute(
            select(DocumentLink).where(
                DocumentLink.predecessor_document_id.in_(present_ids),
                DocumentLink.successor_document_id.in_(present_ids),
            )
        )
    ).scalars().all()
    edges = [
        ChainEdge(
            predecessor_document_id=link.predecessor_document_id,
            successor_document_id=link.successor_document_id,
            link_type=link.link_type,
        )
        for link in link_rows
    ]

    return DocumentChain(nodes=nodes, edges=edges)
