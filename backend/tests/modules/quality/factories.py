"""Quality test data builders behind tests/modules/quality/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping,
numbering, docflow and the event-driven lot creation fire exactly as in production. conftest.py
keeps
only the thin pytest fixtures.

``build_inspection_lot_setup`` wires a tenant fully ready for the quality flow: it builds a goods
receipt setup (item + GL accounts + open period + warehouse/bin + GR/IR default + a SENT PO via the
procurement factories), creates a goods receipt whose line is FLAGGED ``requires_inspection=True``,
and POSTS it — so the quality GR handler creates an OPEN inspection lot in the same transaction. The
setup returns the created lot id plus the ids the decision tests need (the item, the receiving bin,
and a SECOND bin used as the BLOCK quarantine destination). ``create_quality_principal`` mirrors the
manufacturing principal pattern with quality.* keys, plus the procurement/finance/inventory setup
keys the API tests need to scaffold a flagged goods receipt over the wire.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.procurement import service as procurement_service
from app.modules.procurement.schemas import GoodsReceiptLineCreate
from app.modules.quality import queries as quality_queries
from tests.modules.procurement.factories import (
    build_goods_receipt,
    build_goods_receipt_setup,
    post_goods_receipt,
)


@dataclass(frozen=True)
class InspectionLotSetup:
    """A tenant with a posted, inspection-FLAGGED goods receipt that auto-created an OPEN inspection
    lot (PLAN 9.1). Plain ids so a rollback (expiring loaded ORM objects) cannot break a follow-up
    payload. ``lot_id`` is the created inspection lot; ``bin_id`` is the receiving bin the stock
    landed in (a SCRAP/BLOCK moves from it); ``blocked_bin_id`` is a second bin in the same
    warehouse
    used as the BLOCK quarantine destination; ``gr_document_id`` is the GR's core_documents id (the
    lot's source + the docflow predecessor)."""

    tenant_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    blocked_bin_id: uuid.UUID
    gr_id: uuid.UUID
    gr_document_id: uuid.UUID
    lot_id: uuid.UUID
    lot_quantity: Decimal
    price_difference_account_id: uuid.UUID
    inventory_account_id: uuid.UUID
    fiscal_year_id: uuid.UUID


async def build_inspection_lot_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    receive_quantity: str = "10",
    po_unit_cost: str = "5",
) -> InspectionLotSetup:
    """Wire a flagged, posted goods receipt so an OPEN inspection lot exists (PLAN 9.1). Builds the
    goods-receipt setup, creates a GR with one line flagged ``requires_inspection=True``, posts it
    (the quality handler creates the lot), and returns the created lot + a second quarantine bin."""
    from tests.modules.inventory.factories import build_bin

    gr_setup = await build_goods_receipt_setup(
        session, tenant_id, po_quantity=receive_quantity, po_unit_cost=po_unit_cost
    )
    blocked_bin = await build_bin(
        session, tenant_id, gr_setup.warehouse_id, code="QI", name="Quality hold"
    )
    gr = await build_goods_receipt(
        session,
        tenant_id,
        po_id=gr_setup.po_id,
        warehouse_id=gr_setup.warehouse_id,
        lines=[
            GoodsReceiptLineCreate(
                purchase_order_line_id=gr_setup.po_line_id,
                bin_id=gr_setup.bin_id,
                received_quantity=Decimal(receive_quantity),
                requires_inspection=True,
            )
        ],
    )
    await post_goods_receipt(session, tenant_id, gr.id)
    with tenant_context(tenant_id):
        gr_reloaded = await procurement_service.get_goods_receipt(session, tenant_id, gr.id)
        gr_document_id = gr_reloaded.document_id
        lots = await quality_queries.lots_for_goods_receipt(
            session, tenant_id, gr_document_id
        )
    return InspectionLotSetup(
        tenant_id=tenant_id,
        item_id=gr_setup.item_id,
        warehouse_id=gr_setup.warehouse_id,
        bin_id=gr_setup.bin_id,
        blocked_bin_id=blocked_bin.id,
        gr_id=gr.id,
        gr_document_id=gr_document_id,
        lot_id=lots[0].id,
        lot_quantity=Decimal(receive_quantity),
        price_difference_account_id=gr_setup.price_difference_account_id,
        inventory_account_id=gr_setup.inventory_account_id,
        fiscal_year_id=gr_setup.fiscal_year_id,
    )


# --- Principals ---------------------------------------------------------------

# EVERY registered quality.* key (importing quality.constants registers them), so a new quality
# permission is auto-granted to the full-rights principal (self-extending). The flagged goods
# receipt
# the lot derives from is seeded through the db_session factories (system context), not over the
# wire,
# so the principal needs only the quality keys to drive the inspection-lot endpoints — the
# production_api precedent (setup seeded via factories, client drives only the module's own routes).
_QUALITY_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("quality.")))


@dataclass(frozen=True)
class QualityPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_quality_principal(
    session: AsyncSession,
    slug: str = "qm-acme",
    email: str = "qa@qm-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] | None = None,
) -> QualityPrincipal:
    """Provision a tenant + user and grant a role with the quality permission keys through the real
    services (D-025); ``keys`` narrows the grant for the 403 RBAC tests (None = full)."""
    grant = keys if keys is not None else _QUALITY_KEYS
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Quality", grant, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return QualityPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )
