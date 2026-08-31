"""#165 / D-075: the classification gate on the tenant Owner's default permission grant, plus the
two properties of the catalog sync that grant depends on.

The grant is SUBTRACTIVE — ``catalog_keys() - _WITHHELD_FROM_FIRST_ADMIN`` — which is fail-open for
every key that does not exist yet: ship ``platform.tenant.suspend`` or ``hr.employee.read_ssn`` in
some module's ``constants.py`` and it joins the default grant of every future tenant Owner silently,
which is #165's own failure shape inverted. So the whole catalog is pinned here. **Adding a
permission key? This test fails on purpose.** Decide first whether the new key belongs in
``_WITHHELD_FROM_FIRST_ADMIN`` (onboarding.py) — it does if it exposes an individual's pay or PII,
or acts on the PLATFORM rather than inside one tenant — then add it below. The pin is deliberately
literal, not ``sorted(catalog_keys())``: a computed expectation would agree with whatever the
catalog becomes, which is the guard doing nothing.
"""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.events import run_in_uow
from app.core.models import Permission
from app.core.rbac import catalog_keys
from app.core.tenancy import system_context
from app.modules.industry import onboarding

_PASSWORD = "correct-horse-battery"

# Every key the running app declares. See the module docstring before touching this list.
_CLASSIFIED_KEYS = frozenset(
    [
        "admin.apikey.manage",
        "admin.audit.read",
        "admin.numbering.read",
        "admin.role.manage",
        "admin.tenant.manage",
        "admin.user.manage",
        "core.document.read",
        "core.setting.manage",
        "crm.activity.manage",
        "crm.activity.read",
        "crm.lead.manage",
        "crm.lead.read",
        "crm.opportunity.convert",
        "crm.opportunity.manage",
        "crm.opportunity.read",
        "finance.account.manage",
        "finance.account.read",
        "finance.allocation.manage",
        "finance.allocation.run",
        "finance.ap.manage",
        "finance.ap.pay",
        "finance.ap.read",
        "finance.ar.collect",
        "finance.ar.manage",
        "finance.ar.read",
        "finance.asset.manage",
        "finance.asset.read",
        "finance.bank.import",
        "finance.bank.read",
        "finance.bank.reconcile",
        "finance.costcenter.manage",
        "finance.costcenter.read",
        "finance.depreciation.run",
        "finance.fx.manage",
        "finance.fx.revalue",
        "finance.journal.post",
        "finance.journal.read",
        "finance.journal.reverse",
        "finance.period.manage",
        "finance.period.read",
        "finance.profitcenter.manage",
        "finance.profitcenter.read",
        "finance.statements.read",
        "finance.tax.manage",
        "finance.tax.read",
        # Phase 20.1. GRANTED, on the same reading as the reservation keys below: room types,
        # rooms, rates and the housekeeping board are the property's own operational data, and
        # nothing here is behind the D-009 masking gate. `housekeeping.manage` is a SEPARATE key
        # from `rooms.manage` because taking a room out of service has a revenue consequence
        # (D-085) — a distinction that shapes the roles an owner DELEGATES, not what the owner
        # holds; the Owner grant stays subtractive, so a curated subset cannot rot the next time
        # this module ships a key.
        "hospitality.housekeeping.manage",
        "hospitality.menu.manage",
        "hospitality.menu.read",
        # Phase 21. GRANTED to the Owner, not withheld: a reservation book is operational data the
        # property's owner runs the floor from, the same standing as the CRM customer records and
        # the HR employee rows the Owner already holds. The withheld set is narrower on purpose —
        # it is the D-009 masking gate (pay, national id, bank account) plus the platform's own
        # provisioning key, and guest contact detail is not behind that gate. Note the asymmetry
        # this preserves: `.read` is the whole night's guest list and stays a STAFF key, while
        # `.book` is the width a website credential is minted at (D-077), so the Owner holding all
        # three does not widen what a leaked website key can reach.
        "hospitality.reservation.book",
        "hospitality.reservation.manage",
        "hospitality.reservation.read",
        "hospitality.rooms.manage",
        "hospitality.rooms.read",
        "hospitality.ticket.manage",
        "hospitality.ticket.read",
        "hospitality.ticket.settle",
        "hr.department.manage",
        "hr.department.read",
        "hr.employee.manage",
        "hr.employee.read",
        "hr.employee.read_compensation",
        "hr.leave.approve",
        "hr.leave.read",
        "hr.leave.request",
        "hr.leave_type.manage",
        "hr.leave_type.read",
        "hr.payroll.manage",
        "hr.payroll.post",
        "hr.payroll.read",
        "hr.position.manage",
        "hr.position.read",
        "hr.timesheet.approve",
        "hr.timesheet.manage",
        "hr.timesheet.read",
        "industry.template.apply",
        "industry.template.read",
        "inventory.bin.manage",
        "inventory.bin.read",
        "inventory.category.manage",
        "inventory.category.read",
        "inventory.count.manage",
        "inventory.count.post",
        "inventory.count.read",
        "inventory.item.manage",
        "inventory.item.read",
        "inventory.move.create",
        "inventory.move.read",
        "inventory.uom.manage",
        "inventory.uom.read",
        "inventory.valuation.read",
        "inventory.warehouse.manage",
        "inventory.warehouse.read",
        "maintenance.equipment.manage",
        "maintenance.equipment.read",
        "maintenance.order.complete",
        "maintenance.order.manage",
        "maintenance.order.read",
        "maintenance.plan.manage",
        "maintenance.plan.read",
        "maintenance.plan.run",
        "manufacturing.bom.manage",
        "manufacturing.bom.read",
        "manufacturing.mrp.read",
        "manufacturing.mrp.run",
        "manufacturing.planned_order.manage",
        "manufacturing.planned_order.read",
        "manufacturing.production_order.execute",
        "manufacturing.production_order.manage",
        "manufacturing.production_order.read",
        "manufacturing.production_order.release",
        "manufacturing.routing.manage",
        "manufacturing.routing.read",
        "manufacturing.workcenter.manage",
        "manufacturing.workcenter.read",
        "onboarding.tenant.create",
        "procurement.approval_rule.manage",
        "procurement.goods_receipt.manage",
        "procurement.goods_receipt.post",
        "procurement.goods_receipt.read",
        "procurement.invoice_match.manage",
        "procurement.invoice_match.post",
        "procurement.invoice_match.read",
        "procurement.po.approve",
        "procurement.po.manage",
        "procurement.po.read",
        "procurement.requisition.approve",
        "procurement.requisition.manage",
        "procurement.requisition.read",
        "procurement.rfq.manage",
        "procurement.rfq.read",
        "procurement.vendor.manage",
        "procurement.vendor.read",
        "projects.project.manage",
        "projects.project.read",
        "projects.report.read",
        "projects.wbs.manage",
        "projects.wbs.read",
        "quality.inspection.decide",
        "quality.inspection.manage",
        "quality.inspection.read",
        "reporting.dashboard.read",
        "reporting.report.run",
        "sales.billing.manage",
        "sales.billing.post",
        "sales.billing.read",
        "sales.customer.manage",
        "sales.customer.read",
        "sales.delivery.manage",
        "sales.delivery.post",
        "sales.delivery.read",
        "sales.order.confirm",
        "sales.order.credit_release",
        "sales.order.manage",
        "sales.order.read",
        "sales.pricelist.manage",
        "sales.pricelist.read",
        "sales.quote.manage",
        "sales.quote.read",
        "sales.return.manage",
        "sales.return.post",
        "sales.return.read",
    ]
)


async def _onboard(session, slug: str) -> onboarding.OnboardingResult:
    """Onboard through run_in_uow (the router's path) and — unlike the helper in test_onboarding.py
    — WITHOUT pre-syncing the permission catalog, which is the condition the tests below prove."""
    holder: dict[str, onboarding.OnboardingResult] = {}

    async def _work() -> None:
        holder["result"] = await onboarding.onboard_tenant(
            session,
            company_name=slug.title(),
            slug=slug,
            template_name="manufacturing",
            admin_email=f"owner@{slug}.test",
            admin_password=_PASSWORD,
        )

    await run_in_uow(session, _work)
    return holder["result"]


async def _catalog_row_count(session) -> int:
    with system_context():
        return (
            await session.execute(select(func.count()).select_from(Permission))
        ).scalar_one()


def test_every_permission_key_is_classified_for_the_owner_grant():
    """The gate itself. Read the module docstring: a key that appears here without a decision about
    ``_WITHHELD_FROM_FIRST_ADMIN`` is a silent privilege grant to every tenant provisioned after it
    ships."""
    assert catalog_keys() == _CLASSIFIED_KEYS


def test_withheld_keys_are_real_catalog_keys():
    """A typo in the withheld set would subtract nothing and grant the key it names — silently,
    because subtracting a key that is not in the catalog is not an error."""
    assert catalog_keys() >= onboarding._WITHHELD_FROM_FIRST_ADMIN


async def test_onboard_syncs_the_permission_catalog_itself(db_session):
    """Nothing syncs ``core_permissions`` except ``seed.py`` — not a migration, not the app
    lifespan — so on a migrated-but-unseeded deploy the table is EMPTY and every key the Owner grant
    asks for is un-grantable (``create_role`` raises ``rbac.unknown_permission``, a 422 that rolls
    the whole provision back). Onboarding therefore syncs it itself; this proves that, rather than
    riding on a sync some earlier fixture happened to run."""
    assert await _catalog_row_count(db_session) == 0
    await _onboard(db_session, "unseeded-co")
    assert await _catalog_row_count(db_session) == len(catalog_keys())


async def test_onboard_survives_a_losing_catalog_sync_race(db_session, monkeypatch):
    """``core_permissions`` is GLOBAL and onboarding is its only writer on a request path, so two
    onboardings against an unseeded deploy both see a key missing and both insert it; the loser gets
    a unique-constraint violation. Without the savepoint that violation kills the OUTER transaction
    — tenant, Owner, template, all of it — for an operation that had already succeeded elsewhere.
    Simulated by failing the first sync AFTER it has queued its inserts (a real collision needs two
    concurrent transactions); the retry must still leave a complete catalog and a provisioned
    tenant."""
    real = onboarding.sync_permission_catalog
    calls: list[int] = []

    async def _loses_once(session):
        await real(session)
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("INSERT INTO core_permissions", {}, Exception("duplicate key"))

    monkeypatch.setattr(onboarding, "sync_permission_catalog", _loses_once)
    result = await _onboard(db_session, "racy-co")
    assert calls == [1, 1]
    assert result.slug == "racy-co"
    assert await _catalog_row_count(db_session) == len(catalog_keys())
