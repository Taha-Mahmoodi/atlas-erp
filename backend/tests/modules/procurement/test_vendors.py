"""Vendor master service tests (PLAN 6.1): CRUD + validation (code unique, currency exists in
finance, payment terms >= 0, status transitions). Exercises the real service layer under the tenant
context (D-025), with the cross-module currency seeded in finance.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.procurement import queries, service
from app.modules.procurement.constants import DEFAULT_PAYMENT_TERMS_DAYS, VendorStatus
from app.modules.procurement.schemas import VendorCreate, VendorUpdate
from tests.modules.procurement.conftest import ProcurementSetup
from tests.modules.procurement.factories import build_vendor, seed_currency


async def test_create_vendor_defaults(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A vendor created with the minimum fields gets ACTIVE status and the NET30 default terms."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id)
    assert vendor.status == VendorStatus.ACTIVE.value
    assert vendor.payment_terms_days == DEFAULT_PAYMENT_TERMS_DAYS
    assert vendor.default_currency_code == "USD"


async def test_vendor_code_unique_per_tenant(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A duplicate vendor_code in the same tenant is a friendly ConflictError."""
    await build_vendor(db_session, procurement_setup.tenant_id, vendor_code="DUP")
    with pytest.raises(ConflictError) as err, tenant_context(procurement_setup.tenant_id):
        await service.create_vendor(
            db_session,
            procurement_setup.tenant_id,
            VendorCreate(vendor_code="DUP", name="Other", default_currency_code="USD"),
        )
    assert err.value.code == "procurement.vendor_code_conflict"


async def test_create_vendor_unknown_currency_rejected(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A default currency not in finance's catalog is a ValidationFailedError (D-029)."""
    with pytest.raises(ValidationFailedError) as err, tenant_context(procurement_setup.tenant_id):
        await service.create_vendor(
            db_session,
            procurement_setup.tenant_id,
            VendorCreate(vendor_code="V-EUR", name="Euro vendor", default_currency_code="EUR"),
        )
    assert err.value.code == "procurement.currency_not_found"


async def test_negative_payment_terms_rejected_by_schema() -> None:
    """payment_terms_days < 0 is refused at the schema boundary (ge=0); the DB CHECK is the
    backstop, so the service never sees a negative value."""
    with pytest.raises(ValueError):
        VendorCreate(
            vendor_code="V-NEG",
            name="Neg terms",
            default_currency_code="USD",
            payment_terms_days=-5,
        )


async def test_update_vendor_fields_and_currency_revalidated(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """A PATCH updates mutable fields; a changed currency is re-validated against finance."""
    vendor = await build_vendor(db_session, procurement_setup.tenant_id, vendor_code="V-UPD")
    with tenant_context(procurement_setup.tenant_id):
        updated = await service.update_vendor(
            db_session,
            procurement_setup.tenant_id,
            vendor.id,
            VendorUpdate(name="Renamed", payment_terms_days=45),
        )
        await db_session.commit()
    assert updated.name == "Renamed"
    assert updated.payment_terms_days == 45

    # Seed EUR, then a currency switch is accepted because EUR now exists.
    await seed_currency(db_session, procurement_setup.tenant_id, code="EUR", name="Euro")
    with tenant_context(procurement_setup.tenant_id):
        switched = await service.update_vendor(
            db_session,
            procurement_setup.tenant_id,
            vendor.id,
            VendorUpdate(default_currency_code="EUR"),
        )
        await db_session.commit()
    assert switched.default_currency_code == "EUR"


@pytest.mark.parametrize(
    "target",
    [VendorStatus.BLOCKED, VendorStatus.INACTIVE, VendorStatus.ACTIVE],
)
async def test_status_transitions_unrestricted(
    db_session: AsyncSession, procurement_setup: ProcurementSetup, target: VendorStatus
) -> None:
    """Status moves freely between ACTIVE/BLOCKED/INACTIVE — no terminal state (constants doc)."""
    vendor = await build_vendor(
        db_session, procurement_setup.tenant_id, vendor_code=f"V-{target.value}"
    )
    # Walk ACTIVE -> BLOCKED -> INACTIVE -> target to prove every edge is allowed.
    for step in (VendorStatus.BLOCKED, VendorStatus.INACTIVE, target):
        with tenant_context(procurement_setup.tenant_id):
            updated = await service.update_vendor(
                db_session,
                procurement_setup.tenant_id,
                vendor.id,
                VendorUpdate(status=step),
            )
            await db_session.commit()
        assert updated.status == step.value


async def test_get_unknown_vendor_404(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    with pytest.raises(NotFoundError) as err, tenant_context(procurement_setup.tenant_id):
        await service.get_vendor(db_session, procurement_setup.tenant_id, uuid.uuid4())
    assert err.value.code == "procurement.vendor_not_found"


# --- queries interface (the contract 6.2+/finance reporting use) --------------


async def test_queries_resolve_partner_and_terms(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    """``get_vendor_for_partner`` (= AP partner_id resolution, D-029) and the terms/currency reads
    return the vendor's master fields."""
    vendor = await build_vendor(
        db_session,
        procurement_setup.tenant_id,
        vendor_code="V-Q",
        payment_terms_days=60,
    )
    with tenant_context(procurement_setup.tenant_id):
        # partner_id IS the vendor id (finance stores it opaquely).
        resolved = await queries.get_vendor_for_partner(
            db_session, procurement_setup.tenant_id, vendor.id
        )
        assert resolved is not None and resolved.id == vendor.id
        assert await queries.vendor_exists(
            db_session, procurement_setup.tenant_id, vendor.id
        )
        assert (
            await queries.vendor_payment_terms_days(
                db_session, procurement_setup.tenant_id, vendor.id
            )
            == 60
        )
        assert (
            await queries.vendor_default_currency(
                db_session, procurement_setup.tenant_id, vendor.id
            )
            == "USD"
        )


async def test_queries_unknown_vendor_returns_none(
    db_session: AsyncSession, procurement_setup: ProcurementSetup
) -> None:
    with tenant_context(procurement_setup.tenant_id):
        assert (
            await queries.get_vendor(db_session, procurement_setup.tenant_id, uuid.uuid4())
            is None
        )
        assert not await queries.vendor_exists(
            db_session, procurement_setup.tenant_id, uuid.uuid4()
        )
        assert (
            await queries.vendor_payment_terms_days(
                db_session, procurement_setup.tenant_id, uuid.uuid4()
            )
            is None
        )
