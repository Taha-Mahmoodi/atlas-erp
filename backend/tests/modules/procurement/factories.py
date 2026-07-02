"""Procurement test data builders behind tests/modules/procurement/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping
and audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_procurement_setup`` wires a tenant ready to create vendors and approved items: it seeds a
currency (USD) in finance — the cross-module read ``default_currency_code`` validates against — and
an inventory item (via the inventory builders) so approved-item validation has a real item to point
at. ``create_procurement_principal`` mirrors the finance/inventory principal pattern with
procurement.* keys (and supports a narrowed ``keys`` grant for the 403 RBAC tests), plus the finance
+ inventory setup keys the cross-module-aware tests need.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.finance.constants import (
    AP_CONTROL,
    GR_IR_CLEARING,
    PURCHASE_PRICE_VARIANCE,
    AccountType,
)
from app.modules.finance.schemas import AccountCreate
from app.modules.procurement import service
from app.modules.procurement.constants import ApprovalDocumentType
from app.modules.procurement.models import (
    ApprovalRule,
    GoodsReceipt,
    InvoiceMatch,
    PurchaseOrder,
    PurchaseRequisition,
    Rfq,
    Vendor,
    VendorApprovedItem,
)
from app.modules.procurement.schemas import (
    ApprovalRuleCreate,
    GoodsReceiptCreate,
    GoodsReceiptLineCreate,
    InvoiceMatchCreate,
    InvoiceMatchLineCreate,
    PurchaseOrderCreate,
    PurchaseOrderLineCreate,
    RequisitionCreate,
    RequisitionLineCreate,
    RfqCreate,
    RfqLineCreate,
    VendorApprovedItemCreate,
    VendorCreate,
)

# EVERY registered procurement.* key (importing procurement.constants registers them), so a new
# procurement permission is auto-granted to the full-rights principal (self-extending).
_PROCUREMENT_KEYS = tuple(
    sorted(key for key in catalog_keys() if key.startswith("procurement."))
)


async def seed_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str = "USD", name: str = "US Dollar"
) -> str:
    """Create a currency in finance through the real service (D-025) so the vendor's
    ``default_currency_code`` has something to validate against (D-029). Returns the code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(session, tenant_id, code=code, name=name)
        await session.commit()
    return code


async def build_vendor(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_code: str = "V-001",
    name: str = "Acme Supplies",
    default_currency_code: str = "USD",
    **kwargs: object,
) -> Vendor:
    """Create a vendor through the real service (D-025). ``kwargs`` overrides any VendorCreate field
    (status, payment_terms_days, email, ...)."""
    payload_fields: dict[str, object] = {
        "vendor_code": vendor_code,
        "name": name,
        "default_currency_code": default_currency_code,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        vendor = await service.create_vendor(
            session, tenant_id, VendorCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return vendor


async def build_approved_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    vendor_item_code: str | None = None,
    is_active: bool = True,
) -> VendorApprovedItem:
    """Approve an item for a vendor through the real service (D-025)."""
    with tenant_context(tenant_id):
        approved = await service.add_approved_item(
            session,
            tenant_id,
            vendor_id,
            VendorApprovedItemCreate(
                item_id=item_id, vendor_item_code=vendor_item_code, is_active=is_active
            ),
        )
        await session.commit()
    return approved


@dataclass(frozen=True)
class ProcurementSetup:
    """A tenant ready to create vendors + approved items: the USD currency code (seeded in finance,
    so a vendor's default_currency_code validates) and a real inventory item id (so approved-item
    validation has something to point at). Plain ids so a rollback (expiring loaded ORM objects)
    cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    currency_code: str
    item_id: uuid.UUID
    uom_id: uuid.UUID


async def build_procurement_setup(
    session: AsyncSession, tenant_id: uuid.UUID
) -> ProcurementSetup:
    """Seed a USD currency (finance) and a STOCKED inventory item (inventory), so vendor creation
    and approved-item validation both have real cross-module data to validate against (D-029)."""
    # Imported lazily so the procurement factories do not hard-depend on the inventory test package
    # at import time (it is only needed when a real item is required).
    from tests.modules.inventory.factories import build_inventory_setup, build_item

    code = await seed_currency(session, tenant_id)
    inv = await build_inventory_setup(session, tenant_id)
    item = await build_item(
        session,
        tenant_id,
        item_code="ITEM-1",
        category_id=inv.category_id,
        base_uom_id=inv.ea_uom_id,
    )
    return ProcurementSetup(
        tenant_id=tenant_id, currency_code=code, item_id=item.id, uom_id=inv.ea_uom_id
    )


# --- P2P documents (PLAN 6.2) -------------------------------------------------


async def build_requisition(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    currency_code: str = "USD",
    quantity: str = "10",
    estimated_unit_cost: str | None = "5",
    requested_by: uuid.UUID | None = None,
) -> PurchaseRequisition:
    """Create a DRAFT requisition with one line through the real service (D-025)."""
    with tenant_context(tenant_id):
        req = await service.create_requisition(
            session,
            tenant_id,
            RequisitionCreate(
                requested_by=requested_by,
                lines=[
                    RequisitionLineCreate(
                        item_id=item_id,
                        quantity=Decimal(quantity),
                        uom_id=uom_id,
                        estimated_unit_cost=(
                            None if estimated_unit_cost is None else Decimal(estimated_unit_cost)
                        ),
                        currency_code=currency_code,
                    )
                ],
            ),
        )
        await session.commit()
    return req


async def build_rfq(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    currency_code: str = "USD",
    quantity: str = "10",
) -> Rfq:
    """Create a DRAFT RFQ with one line through the real service (D-025)."""
    with tenant_context(tenant_id):
        rfq = await service.create_rfq(
            session,
            tenant_id,
            RfqCreate(
                vendor_id=vendor_id,
                currency_code=currency_code,
                lines=[
                    RfqLineCreate(
                        item_id=item_id, quantity=Decimal(quantity), uom_id=uom_id
                    )
                ],
            ),
        )
        await session.commit()
    return rfq


async def build_po(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    vendor_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    quantity: str = "10",
    unit_cost: str = "5",
    currency_code: str | None = None,
) -> PurchaseOrder:
    """Create a DRAFT PO with one line through the real service (D-025). The vendor must be ACTIVE
    and the item approved for it (the caller seeds that)."""
    with tenant_context(tenant_id):
        po = await service.create_purchase_order(
            session,
            tenant_id,
            PurchaseOrderCreate(
                vendor_id=vendor_id,
                currency_code=currency_code,
                lines=[
                    PurchaseOrderLineCreate(
                        item_id=item_id,
                        quantity=Decimal(quantity),
                        uom_id=uom_id,
                        unit_cost=Decimal(unit_cost),
                    )
                ],
            ),
        )
        await session.commit()
    return po


async def build_approval_rule(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    document_type: ApprovalDocumentType,
    threshold_amount: str,
    currency_code: str = "USD",
    is_active: bool = True,
) -> ApprovalRule:
    """Create an approval-threshold rule through the real service (D-025)."""
    with tenant_context(tenant_id):
        rule = await service.create_approval_rule(
            session,
            tenant_id,
            ApprovalRuleCreate(
                document_type=document_type,
                threshold_amount=Decimal(threshold_amount),
                currency_code=currency_code,
                is_active=is_active,
            ),
        )
        await session.commit()
    return rule


# --- Goods receipts (PLAN 6.3) ------------------------------------------------


@dataclass(frozen=True)
class GoodsReceiptSetup:
    """A tenant fully wired to create + POST a goods receipt against a SENT PO (PLAN 6.3): a STOCKED
    item whose category wires the GL accounts, an OPEN fiscal year, a warehouse + bin, the GR/IR
    clearing account mapped as a posting default, an ACTIVE vendor with the item approved, and a
    SENT PO for ``po_quantity`` @ ``po_unit_cost``. Plain ids so a rollback (expiring loaded ORM
    objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    inventory_account_id: uuid.UUID
    cogs_account_id: uuid.UUID
    price_difference_account_id: uuid.UUID
    gr_ir_account_id: uuid.UUID
    fiscal_year_id: uuid.UUID
    vendor_id: uuid.UUID
    po_id: uuid.UUID
    po_line_id: uuid.UUID
    po_quantity: Decimal
    po_unit_cost: Decimal


async def _map_gr_ir_clearing(
    session: AsyncSession, tenant_id: uuid.UUID
) -> uuid.UUID:
    """Create a GR/IR clearing LIABILITY account and map it as the ``gr_ir_clearing`` posting
    default (D-041) so a goods receipt can credit it. Returns the account id."""
    with tenant_context(tenant_id):
        account = await finance_service.create_account(
            session,
            tenant_id,
            AccountCreate(
                code="2150", name="GR/IR clearing", account_type=AccountType.LIABILITY
            ),
        )
        await session.commit()
        await finance_service.set_posting_default(
            session, tenant_id, GR_IR_CLEARING, account.id
        )
        await session.commit()
    return account.id


async def build_goods_receipt_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    po_quantity: str = "10",
    po_unit_cost: str = "5",
    tracking_mode: str = "NONE",
    map_gr_ir: bool = True,
) -> GoodsReceiptSetup:
    """Wire a SENT PO + the GR/IR clearing default so a goods receipt can be created and posted
    (PLAN 6.3). Builds the inventory stock setup (item + GL accounts + open period + warehouse/bin),
    maps GR/IR clearing (unless ``map_gr_ir`` is False — the unmapped-error test), seeds a USD
    currency + an ACTIVE vendor with the item approved, then creates and SENDS a PO."""
    from tests.modules.inventory.factories import build_stock_setup

    stock = await build_stock_setup(session, tenant_id, tracking_mode=tracking_mode)
    gr_ir_account_id = (
        await _map_gr_ir_clearing(session, tenant_id)
        if map_gr_ir
        else uuid.uuid4()  # a placeholder id never mapped (the unmapped-error path)
    )
    await seed_currency(session, tenant_id)
    vendor = await build_vendor(session, tenant_id)
    await build_approved_item(session, tenant_id, vendor.id, stock.item_id)

    with tenant_context(tenant_id):
        po = await service.create_purchase_order(
            session,
            tenant_id,
            PurchaseOrderCreate(
                vendor_id=vendor.id,
                lines=[
                    PurchaseOrderLineCreate(
                        item_id=stock.item_id,
                        quantity=Decimal(po_quantity),
                        uom_id=stock.base_uom_id,
                        unit_cost=Decimal(po_unit_cost),
                    )
                ],
            ),
        )
        await session.commit()
        await service.send_purchase_order(session, tenant_id, po.id)
        await session.commit()
        po_lines = await service.get_purchase_order_lines(session, tenant_id, po.id)

    return GoodsReceiptSetup(
        tenant_id=tenant_id,
        item_id=stock.item_id,
        warehouse_id=stock.warehouse_id,
        bin_id=stock.bin_a_id,
        inventory_account_id=stock.inventory_account_id,
        cogs_account_id=stock.cogs_account_id,
        price_difference_account_id=stock.price_difference_account_id,
        gr_ir_account_id=gr_ir_account_id,
        fiscal_year_id=stock.fiscal_year_id,
        vendor_id=vendor.id,
        po_id=po.id,
        po_line_id=po_lines[0].id,
        po_quantity=Decimal(po_quantity),
        po_unit_cost=Decimal(po_unit_cost),
    )


async def build_goods_receipt(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    po_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    lines: list[GoodsReceiptLineCreate],
    receipt_date=None,
) -> GoodsReceipt:
    """Create a DRAFT goods receipt through the real service inside a uow (D-025). Returns the
    persisted GR re-read after the uow commit."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            gr = await service.create_goods_receipt(
                session,
                tenant_id,
                GoodsReceiptCreate(
                    purchase_order_id=po_id,
                    warehouse_id=warehouse_id,
                    receipt_date=receipt_date,
                    lines=lines,
                ),
            )
            holder["id"] = gr.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_goods_receipt(session, tenant_id, holder["id"])


async def post_goods_receipt(
    session: AsyncSession, tenant_id: uuid.UUID, gr_id: uuid.UUID
) -> GoodsReceipt:
    """Post a DRAFT goods receipt through the real service inside a uow (D-025) — the full chain (GR
    + stock moves + GR/IR journals + PO update). Returns the GR re-read after commit."""
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.post_goods_receipt(session, tenant_id, gr_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_goods_receipt(session, tenant_id, gr_id)


# --- Invoice matches (PLAN 6.4) -----------------------------------------------


@dataclass(frozen=True)
class InvoiceMatchSetup:
    """A tenant with a SENT PO that has been RECEIVED (a posted GR raised received_quantity), the
    GR/IR + purchase-price-variance + AP-control posting defaults mapped, ready to create + post a
    3-way match (PLAN 6.4). Plain ids so a rollback (expiring loaded ORM objects) cannot break a
    follow-up payload."""

    tenant_id: uuid.UUID
    item_id: uuid.UUID
    vendor_id: uuid.UUID
    po_id: uuid.UUID
    po_line_id: uuid.UUID
    gr_id: uuid.UUID
    gr_line_id: uuid.UUID
    gr_ir_account_id: uuid.UUID
    ppv_account_id: uuid.UUID
    ap_account_id: uuid.UUID
    po_quantity: Decimal
    po_unit_cost: Decimal


async def _map_posting_default(
    session: AsyncSession, tenant_id: uuid.UUID, purpose: str, code: str, name: str, acct_type
) -> uuid.UUID:
    """Create an account + map it to a posting purpose through the real finance service (D-025)."""
    with tenant_context(tenant_id):
        account = await finance_service.create_account(
            session, tenant_id, AccountCreate(code=code, name=name, account_type=acct_type)
        )
        await session.commit()
        await finance_service.set_posting_default(session, tenant_id, purpose, account.id)
        await session.commit()
    return account.id


async def build_invoice_match_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    po_quantity: str = "10",
    po_unit_cost: str = "5",
    receive_quantity: str | None = None,
    map_ppv: bool = True,
    map_ap: bool = True,
) -> InvoiceMatchSetup:
    """Wire a received PO + the GR/IR, PPV and AP-control posting defaults so a 3-way match can be
    created and posted (PLAN 6.4). Builds the goods-receipt setup (which maps GR/IR), receives
    ``receive_quantity`` (defaults to the full PO quantity) by posting a GR, then maps the PPV and
    AP-control defaults (unless suppressed — the unmapped-error tests)."""
    gr_setup = await build_goods_receipt_setup(
        session, tenant_id, po_quantity=po_quantity, po_unit_cost=po_unit_cost
    )
    recv = receive_quantity if receive_quantity is not None else po_quantity
    gr = await build_goods_receipt(
        session,
        tenant_id,
        po_id=gr_setup.po_id,
        warehouse_id=gr_setup.warehouse_id,
        lines=[
            GoodsReceiptLineCreate(
                purchase_order_line_id=gr_setup.po_line_id,
                bin_id=gr_setup.bin_id,
                received_quantity=Decimal(recv),
            )
        ],
    )
    await post_goods_receipt(session, tenant_id, gr.id)
    with tenant_context(tenant_id):
        gr_lines = await service.get_goods_receipt_lines(session, tenant_id, gr.id)

    ppv_account_id = (
        await _map_posting_default(
            session, tenant_id, PURCHASE_PRICE_VARIANCE, "5910", "PPV", AccountType.EXPENSE
        )
        if map_ppv
        else uuid.uuid4()
    )
    ap_account_id = (
        await _map_posting_default(
            session, tenant_id, AP_CONTROL, "2100", "AP control", AccountType.LIABILITY
        )
        if map_ap
        else uuid.uuid4()
    )
    return InvoiceMatchSetup(
        tenant_id=tenant_id,
        item_id=gr_setup.item_id,
        vendor_id=gr_setup.vendor_id,
        po_id=gr_setup.po_id,
        po_line_id=gr_setup.po_line_id,
        gr_id=gr.id,
        gr_line_id=gr_lines[0].id,
        gr_ir_account_id=gr_setup.gr_ir_account_id,
        ppv_account_id=ppv_account_id,
        ap_account_id=ap_account_id,
        po_quantity=Decimal(po_quantity),
        po_unit_cost=Decimal(po_unit_cost),
    )


async def build_invoice_match(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    po_id: uuid.UUID,
    lines: list[InvoiceMatchLineCreate],
    vendor_invoice_ref: str | None = "VINV-1",
    tax_code_id: uuid.UUID | None = None,
    invoice_date=None,
) -> InvoiceMatch:
    """Create a DRAFT 3-way match through the real service inside a uow (D-025). Returns the match
    re-read after commit."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(tenant_id):
            match = await service.create_invoice_match(
                session,
                tenant_id,
                InvoiceMatchCreate(
                    purchase_order_id=po_id,
                    vendor_invoice_ref=vendor_invoice_ref,
                    tax_code_id=tax_code_id,
                    invoice_date=invoice_date,
                    lines=lines,
                ),
            )
            holder["id"] = match.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_invoice_match(session, tenant_id, holder["id"])


async def post_invoice_match(
    session: AsyncSession, tenant_id: uuid.UUID, match_id: uuid.UUID
) -> InvoiceMatch:
    """Post a match through the real service inside a uow (D-025) — the full chain (match + AP bill
    + GR/IR clearing + PO update). Returns the match re-read after commit."""

    async def work() -> None:
        with tenant_context(tenant_id):
            await service.post_invoice_match(session, tenant_id, match_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_invoice_match(session, tenant_id, match_id)


# --- Principals ---------------------------------------------------------------

# Finance + inventory setup keys the API tests need to scaffold cross-module data through the wire
# (a vendor's currency lives in finance; an approved item points at a real inventory item; a goods
# receipt needs GL accounts, an open period, a GR/IR posting default, and a warehouse + bin — 6.3).
_FINANCE_SETUP_KEYS = (
    "finance.fx.manage",
    "finance.account.manage",
    "finance.period.manage",
)
_INVENTORY_SETUP_KEYS = (
    "inventory.uom.manage",
    "inventory.category.manage",
    "inventory.item.manage",
    "inventory.warehouse.manage",
    "inventory.bin.manage",
    "inventory.move.read",
)
_FULL_KEYS = (*_PROCUREMENT_KEYS, *_FINANCE_SETUP_KEYS, *_INVENTORY_SETUP_KEYS)


@dataclass(frozen=True)
class ProcurementPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_procurement_principal(
    session: AsyncSession,
    slug: str = "proc-acme",
    email: str = "buyer@proc-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _FULL_KEYS,
) -> ProcurementPrincipal:
    """Provision a tenant + user and grant a role with the procurement permission keys (plus the
    finance/inventory setup keys for the cross-module API scaffolding) through the real services
    (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Procurement", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return ProcurementPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )
