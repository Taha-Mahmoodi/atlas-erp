"""Sales test data builders behind tests/modules/sales/conftest.py (STRUCTURE §6/§8.4).

Builders go through the REAL service layer under the tenant context (D-025), so tenancy stamping and
audit fire exactly as in production. conftest.py keeps only the thin pytest fixtures.

``build_sales_setup`` wires a tenant ready to create customers + price lists: it seeds a currency
(USD) in finance — the cross-module read ``default_currency_code`` / a price list's
``currency_code``
validate against — and an inventory item (so price-list-item validation has a real item to point
at).
``create_sales_principal`` mirrors the finance/inventory/procurement principal pattern with sales.*
keys (and supports a narrowed ``keys`` grant for the 403 RBAC tests), plus the finance + inventory
setup keys the cross-module-aware API tests need.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.rbac import catalog_keys, sync_permission_catalog
from app.core.tenancy import system_context, tenant_context
from app.modules.admin.service import assign_role, create_role, provision_tenant, provision_user
from app.modules.finance import service as finance_service
from app.modules.sales import service
from app.modules.sales.models import (
    Customer,
    CustomerGroup,
    Delivery,
    PriceList,
    PriceListItem,
    Quote,
    SalesOrder,
)
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerGroupCreate,
    DeliveryCreate,
    PriceListCreate,
    PriceListItemCreate,
    QuoteCreate,
    QuoteLineCreate,
    SalesOrderCreate,
    SalesOrderLineCreate,
)

# EVERY registered sales.* key (importing sales.constants registers them), so a new sales permission
# is auto-granted to the full-rights principal (self-extending).
_SALES_KEYS = tuple(sorted(key for key in catalog_keys() if key.startswith("sales.")))


async def seed_currency(
    session: AsyncSession, tenant_id: uuid.UUID, code: str = "USD", name: str = "US Dollar"
) -> str:
    """Create a currency in finance through the real service (D-025) so a customer's
    ``default_currency_code`` / a price list's ``currency_code`` have something to validate against
    (D-029). Returns the code."""
    with tenant_context(tenant_id):
        await finance_service.create_currency(session, tenant_id, code=code, name=name)
        await session.commit()
    return code


async def build_customer_group(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "GRP-1",
    name: str = "Wholesale",
) -> CustomerGroup:
    """Create a customer group through the real service (D-025)."""
    with tenant_context(tenant_id):
        group = await service.create_customer_group(
            session, tenant_id, CustomerGroupCreate(code=code, name=name)
        )
        await session.commit()
    return group


async def build_customer(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_code: str = "C-001",
    name: str = "Acme Retail",
    default_currency_code: str = "USD",
    **kwargs: object,
) -> Customer:
    """Create a customer through the real service (D-025). ``kwargs`` overrides any CustomerCreate
    field (status, customer_group_id, credit_limit, payment_terms_days, ...)."""
    payload_fields: dict[str, object] = {
        "customer_code": customer_code,
        "name": name,
        "default_currency_code": default_currency_code,
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        customer = await service.create_customer(
            session, tenant_id, CustomerCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return customer


async def build_price_list(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    code: str = "PL-1",
    name: str = "Standard",
    currency_code: str = "USD",
    valid_from: date | None = None,
    **kwargs: object,
) -> PriceList:
    """Create a price list through the real service (D-025). ``valid_from`` defaults to a fixed
    early
    date so date-window tests are deterministic. ``kwargs`` overrides any PriceListCreate field
    (customer_group_id, valid_to, status, priority, ...)."""
    payload_fields: dict[str, object] = {
        "code": code,
        "name": name,
        "currency_code": currency_code,
        "valid_from": valid_from if valid_from is not None else date(2026, 1, 1),
    }
    payload_fields.update(kwargs)
    with tenant_context(tenant_id):
        price_list = await service.create_price_list(
            session, tenant_id, PriceListCreate(**payload_fields)  # type: ignore[arg-type]
        )
        await session.commit()
    return price_list


async def build_price_list_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    price_list_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    unit_price: str = "10",
    min_quantity: str = "0",
) -> PriceListItem:
    """Add a base price for an item to a price list through the real service (D-025)."""
    with tenant_context(tenant_id):
        item = await service.add_price_list_item(
            session,
            tenant_id,
            price_list_id,
            PriceListItemCreate(
                item_id=item_id,
                unit_price=Decimal(unit_price),
                min_quantity=Decimal(min_quantity),
            ),
        )
        await session.commit()
    return item


@dataclass(frozen=True)
class SalesSetup:
    """A tenant ready to create customers + price lists: the USD currency code (seeded in finance,
    so
    a customer's default_currency_code / a price list's currency_code validate) and a real inventory
    item id (so price-list-item validation has something to point at). Plain ids so a rollback
    (expiring loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    currency_code: str
    item_id: uuid.UUID
    uom_id: uuid.UUID


async def build_sales_setup(session: AsyncSession, tenant_id: uuid.UUID) -> SalesSetup:
    """Seed a USD currency (finance) and an inventory item (inventory), so customer creation and
    price-list-item validation both have real cross-module data to validate against (D-029). The
    item's EA base UoM id is exposed for 7.2 quote/order lines."""
    # Imported lazily so the sales factories do not hard-depend on the inventory test package at
    # import time (it is only needed when a real item is required).
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
    return SalesSetup(
        tenant_id=tenant_id, currency_code=code, item_id=item.id, uom_id=inv.ea_uom_id
    )


# --- Quotes + orders (PLAN 7.2) -----------------------------------------------


async def build_quote(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    quantity: str = "5",
    unit_price: str = "10",
    valid_until: date | None = None,
    **line_kwargs: object,
) -> Quote:
    """Create a DRAFT quote with one line through the real service inside a uow (D-025), so
    numbering + docflow fire as in production. ``line_kwargs`` overrides the line (discount_type,
    discount_value, ...)."""
    holder: dict[str, uuid.UUID] = {}
    line_fields: dict[str, object] = {
        "item_id": item_id,
        "quantity": Decimal(quantity),
        "uom_id": uom_id,
        "unit_price": Decimal(unit_price),
    }
    line_fields.update(line_kwargs)

    async def work() -> None:
        with tenant_context(tenant_id):
            quote = await service.create_quote(
                session,
                tenant_id,
                QuoteCreate(
                    customer_id=customer_id,
                    valid_until=valid_until,
                    lines=[QuoteLineCreate(**line_fields)],  # type: ignore[arg-type]
                ),
            )
            holder["id"] = quote.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_quote(session, tenant_id, holder["id"])


async def build_sales_order(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    customer_id: uuid.UUID,
    item_id: uuid.UUID,
    uom_id: uuid.UUID,
    quantity: str = "5",
    unit_price: str = "10",
    **line_kwargs: object,
) -> SalesOrder:
    """Create a DRAFT sales order with one line through the real service inside a uow (D-025). The
    customer must be ACTIVE. ``line_kwargs`` overrides the line (discount, tax_code_id, ...)."""
    holder: dict[str, uuid.UUID] = {}
    line_fields: dict[str, object] = {
        "item_id": item_id,
        "quantity": Decimal(quantity),
        "uom_id": uom_id,
        "unit_price": Decimal(unit_price),
    }
    line_fields.update(line_kwargs)

    async def work() -> None:
        with tenant_context(tenant_id):
            order = await service.create_sales_order(
                session,
                tenant_id,
                SalesOrderCreate(
                    customer_id=customer_id,
                    lines=[SalesOrderLineCreate(**line_fields)],  # type: ignore[arg-type]
                ),
            )
            holder["id"] = order.id

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_sales_order(session, tenant_id, holder["id"])


async def confirm_sales_order(
    session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID
) -> SalesOrder:
    """Run the confirm gate (ATP + credit) on an order through the real service inside a uow (D-025)
    and return the (possibly CREDIT_BLOCKED) order re-read."""
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.confirm_order(session, tenant_id, order_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_sales_order(session, tenant_id, order_id)


@dataclass(frozen=True)
class OrderSetup:
    """A tenant ready to create + confirm sales orders against real ATP + credit data (PLAN 7.2): a
    customer, a STOCKED item with a warehouse + bin (so on-hand can be seeded), the base UoM, and
    the open 2026 year. The category's inventory + COGS account ids are exposed so 7.3 delivery
    tests
    can assert the posted COGS journal (Dr COGS / Cr Inventory). Plain ids so a rollback (expiring
    loaded ORM objects) cannot break a follow-up payload."""

    tenant_id: uuid.UUID
    currency_code: str
    customer_id: uuid.UUID
    item_id: uuid.UUID
    uom_id: uuid.UUID
    warehouse_id: uuid.UUID
    bin_id: uuid.UUID
    bin_b_id: uuid.UUID
    inventory_account_id: uuid.UUID
    cogs_account_id: uuid.UUID


async def build_order_setup(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    credit_limit: str = "1000000",
    tracking_mode: str = "NONE",
) -> OrderSetup:
    """A stocked item (warehouse + bin + open year, via inventory's build_stock_setup) and an ACTIVE
    customer with a generous default credit limit (PLAN 7.2). on-hand / on-order / open-AR are
    seeded
    by the dedicated helpers below. ``credit_limit`` defaults high so ATP tests are not blocked by
    credit; credit tests pass a small limit. ``tracking_mode`` makes the item
    lot-/serial-tracked for
    the 7.3 lot/serial delivery tests."""
    from tests.modules.inventory.factories import build_stock_setup

    stock = await build_stock_setup(session, tenant_id, tracking_mode=tracking_mode)
    await seed_currency(session, tenant_id)  # USD in finance, for the customer's default currency
    customer = await build_customer(
        session, tenant_id, customer_code="ORD-CUST", credit_limit=Decimal(credit_limit)
    )
    return OrderSetup(
        tenant_id=tenant_id,
        currency_code="USD",
        customer_id=customer.id,
        item_id=stock.item_id,
        uom_id=stock.base_uom_id,
        warehouse_id=stock.warehouse_id,
        bin_id=stock.bin_a_id,
        bin_b_id=stock.bin_b_id,
        inventory_account_id=stock.inventory_account_id,
        cogs_account_id=stock.cogs_account_id,
    )


async def seed_on_hand(
    session: AsyncSession,
    setup: OrderSetup,
    quantity: str,
) -> None:
    """Seed on-hand stock for the setup's item by posting a RECEIPT move (D-025) — the maintained
    quant projection is what sales ATP reads."""
    from tests.modules.inventory.factories import build_stock

    await build_stock(
        session,
        setup.tenant_id,
        setup.item_id,
        setup.bin_id,
        Decimal(quantity),
    )


async def seed_on_order(
    session: AsyncSession,
    setup: OrderSetup,
    quantity: str,
    *,
    unit_cost: str = "5",
) -> None:
    """Seed open-incoming (on-order) stock for the setup's item by raising + SENDING a PO for it
    (D-025) — procurement's open_incoming_quantity (the ATP on-order side) counts SENT PO lines.
    Builds a vendor + approves the item for it, creates the PO, then sends it (auto-approves below
    threshold)."""
    from tests.modules.procurement.factories import (
        build_approved_item,
        build_po,
        build_vendor,
    )

    vendor = await build_vendor(session, setup.tenant_id, vendor_code="ATP-VEND")
    await build_approved_item(session, setup.tenant_id, vendor.id, setup.item_id)
    po = await build_po(
        session,
        setup.tenant_id,
        vendor_id=vendor.id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity=quantity,
        unit_cost=unit_cost,
    )

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            from app.modules.procurement import service as proc_service

            await proc_service.send_purchase_order(session, setup.tenant_id, po.id)

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)


async def seed_open_ar(
    session: AsyncSession,
    setup: OrderSetup,
    amount: str,
) -> None:
    """Seed open AR for the setup's customer by creating + POSTING a customer invoice for ``amount``
    (D-025) — finance's customer_open_balance (the credit-exposure AR side) sums open_amount on
    POSTED customer invoices keyed by the opaque partner_id (= Customer.id, D-029). Creates only the
    two accounts the invoice needs (AR control + revenue), reusing the OPEN year build_order_setup's
    stock setup already created, then posts a one-line invoice."""
    from app.modules.finance import service as finance_svc
    from app.modules.finance.constants import AccountType
    from app.modules.finance.receivables_schemas import (
        CustomerInvoiceCreate,
        CustomerInvoiceLineCreate,
    )
    from app.modules.finance.schemas import AccountCreate

    with tenant_context(setup.tenant_id):
        ar_account = await finance_svc.create_account(
            session,
            setup.tenant_id,
            AccountCreate(code="1200", name="Accounts Receivable", account_type=AccountType.ASSET),
        )
        revenue_account = await finance_svc.create_account(
            session,
            setup.tenant_id,
            AccountCreate(code="4000", name="Sales Revenue", account_type=AccountType.REVENUE),
        )
        await session.commit()
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            invoice = await finance_svc.create_customer_invoice(
                session,
                setup.tenant_id,
                CustomerInvoiceCreate(
                    partner_id=setup.customer_id,
                    partner_name="ORD-CUST",
                    invoice_date=date(2026, 6, 1),
                    due_date=date(2026, 7, 1),
                    currency_code="USD",
                    ar_account_id=ar_account.id,
                    lines=[
                        CustomerInvoiceLineCreate(
                            account_id=revenue_account.id, net_amount=Decimal(amount)
                        )
                    ],
                ),
            )
            await finance_svc.post_customer_invoice(
                session, setup.tenant_id, invoice.id, posting_date=date(2026, 6, 1)
            )
            holder["id"] = invoice.id

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)


# --- Deliveries (PLAN 7.3) ----------------------------------------------------


async def seed_on_hand_lot(
    session: AsyncSession,
    setup: OrderSetup,
    quantity: str,
    *,
    lot_code: str | None = None,
    serial_code: str | None = None,
) -> None:
    """Seed on-hand stock for a tracked item by posting a RECEIPT move that CREATES the lot/serial
    master on the bin (D-025) — a delivery then issues against that existing lot/serial id."""
    from tests.modules.inventory.factories import build_stock

    await build_stock(
        session,
        setup.tenant_id,
        setup.item_id,
        setup.bin_id,
        Decimal(quantity),
        lot_code=lot_code,
        serial_code=serial_code,
    )


async def build_confirmed_order(
    session: AsyncSession,
    setup: OrderSetup,
    *,
    quantity: str = "5",
    unit_price: str = "10",
) -> SalesOrder:
    """Create + CONFIRM a one-line sales order for the setup's item (PLAN 7.3 precondition): a
    confirmed order is the state a delivery picks from. Returns the confirmed order re-read."""
    order = await build_sales_order(
        session,
        setup.tenant_id,
        customer_id=setup.customer_id,
        item_id=setup.item_id,
        uom_id=setup.uom_id,
        quantity=quantity,
        unit_price=unit_price,
    )
    return await confirm_sales_order(session, setup.tenant_id, order.id)


async def build_delivery(
    session: AsyncSession,
    setup: OrderSetup,
    *,
    order_id: uuid.UUID,
    lines: list,
    delivery_date: date | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> Delivery:
    """Create a DRAFT delivery against an order through the real service inside a uow (D-025), so
    numbering + docflow fire as in production. ``lines`` is a list of DeliveryLineCreate.
    Returns the
    persisted delivery re-read after the uow commit."""
    holder: dict[str, uuid.UUID] = {}

    async def work() -> None:
        with tenant_context(setup.tenant_id):
            delivery = await service.create_delivery(
                session,
                setup.tenant_id,
                DeliveryCreate(
                    sales_order_id=order_id,
                    warehouse_id=warehouse_id or setup.warehouse_id,
                    delivery_date=delivery_date,
                    lines=lines,
                ),
            )
            holder["id"] = delivery.id

    with tenant_context(setup.tenant_id):
        await run_in_uow(session, work)
        return await service.get_delivery(session, setup.tenant_id, holder["id"])


async def post_delivery(
    session: AsyncSession, tenant_id: uuid.UUID, delivery_id: uuid.UUID
) -> Delivery:
    """Post a DRAFT delivery through the real service inside a uow (D-025): issues stock + posts the
    COGS journal via the event bus, advances the order. Returns the posted delivery re-read."""
    async def work() -> None:
        with tenant_context(tenant_id):
            await service.post_delivery(session, tenant_id, delivery_id)

    with tenant_context(tenant_id):
        await run_in_uow(session, work)
        return await service.get_delivery(session, tenant_id, delivery_id)


# --- Principals ---------------------------------------------------------------

# Finance + inventory setup keys the API tests need to scaffold cross-module data through the wire
# (a customer's / price list's currency lives in finance; a price-list item points at a real
# inventory item).
_FINANCE_SETUP_KEYS = ("finance.fx.manage",)
_INVENTORY_SETUP_KEYS = (
    "inventory.uom.manage",
    "inventory.category.manage",
    "inventory.item.manage",
)
_FULL_KEYS = (*_SALES_KEYS, *_FINANCE_SETUP_KEYS, *_INVENTORY_SETUP_KEYS)


@dataclass(frozen=True)
class SalesPrincipal:
    tenant_id: uuid.UUID
    tenant_slug: str
    user_id: uuid.UUID
    email: str
    password: str


async def create_sales_principal(
    session: AsyncSession,
    slug: str = "sales-acme",
    email: str = "rep@sales-acme.test",
    password: str = "correct-horse-battery",
    keys: tuple[str, ...] = _FULL_KEYS,
) -> SalesPrincipal:
    """Provision a tenant + user and grant a role with the sales permission keys (plus the
    finance/inventory setup keys for the cross-module API scaffolding) through the real services
    (D-025); ``keys`` narrows the grant for the 403 RBAC tests."""
    tenant = await provision_tenant(session, slug=slug, name=slug.title())
    user = await provision_user(session, tenant.id, email=email, password=password)
    with system_context():
        await sync_permission_catalog(session)
    role = await create_role(session, tenant.id, "Sales", keys, is_system=True)
    await assign_role(session, tenant.id, user.id, role.id, user.token_version)
    await session.commit()
    return SalesPrincipal(
        tenant_id=tenant.id,
        tenant_slug=slug,
        user_id=user.id,
        email=email,
        password=password,
    )
