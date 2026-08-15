"""App wiring: mount every module router + register the cross-module event handlers.

A sanctioned core flat file (STRUCTURE §2 — cross-cutting app wiring): ``create_app`` in
``app.main`` stays focused on the app factory + middleware + exception handlers + health, and
delegates the two blocks that grow with every new module — the router mounting and the D-011
event-handler registration — to this file. Both are pure wiring with no business logic.

``mount_routers(app)`` includes the core platform routers and every business-module router in the
fixed import order; ``register_event_handlers()`` subscribes the cross-module domain-event handlers
in the same deterministic module order (D-011).
"""

from fastapi import FastAPI

from app.core.docflow_router import router as docflow_router
from app.core.jobs_router import router as jobs_router
from app.core.security_router import router as security_router
from app.modules.admin.router import router as admin_router
from app.modules.crm.router import router as crm_router
from app.modules.finance.router import router as finance_router
from app.modules.hospitality.reservation_website_router import (
    website_router as hospitality_reservation_website_router,
)
from app.modules.hospitality.router import router as hospitality_router
from app.modules.hospitality.website_router import router as hospitality_website_router
from app.modules.hr.router import router as hr_router
from app.modules.industry.router import onboarding_router
from app.modules.industry.router import router as industry_router
from app.modules.inventory.router import router as inventory_router
from app.modules.maintenance.router import router as maintenance_router
from app.modules.manufacturing.router import router as manufacturing_router
from app.modules.procurement.router import router as procurement_router
from app.modules.projects.router import router as projects_router
from app.modules.quality.router import router as quality_router
from app.modules.reporting.router import router as reporting_router
from app.modules.sales.router import router as sales_router


def mount_routers(app: FastAPI) -> None:
    """Include the core platform routers + every business-module router, in the fixed import order.

    The order here is also the D-011 handler-registration order (finance, then inventory, ...) once
    modules publish/subscribe events — kept aligned with ``register_event_handlers`` below."""
    # Core platform auth endpoints (D-008): login/refresh/logout/me at /api/v1/auth.
    app.include_router(security_router)
    # Core platform document-flow read endpoint (D-012): GET /api/v1/documents/{id}/chain.
    app.include_router(docflow_router)
    # Core platform background-job polling (PLAN 4P.5/D-032): GET /api/v1/jobs[/{id}].
    app.include_router(jobs_router)
    # Finance module (PLAN 4): chart of accounts + fiscal years/periods at /api/v1/finance.
    # First business module mounted; the fixed import order here is also the D-011 handler
    # registration order (finance, then inventory, ...) once modules publish/subscribe events.
    app.include_router(finance_router)
    # Inventory module (PLAN 5): item masters at /api/v1/inventory. Mounted after finance, the
    # D-011 handler-registration order; inventory reads finance/queries downward (STRUCTURE §5).
    app.include_router(inventory_router)
    # Procurement module (PLAN 6): vendor master at /api/v1/procurement. Mounted after inventory,
    # the D-011 handler-registration order; procurement OWNS the vendor entity and reads
    # finance/queries + inventory/queries downward (STRUCTURE §5 / D-029).
    app.include_router(procurement_router)
    # Sales module (PLAN 7): customer master + condition-style pricing at /api/v1/sales. Mounted
    # after procurement, the D-011 handler-registration order; sales OWNS the customer entity and
    # reads finance/queries + inventory/queries downward (STRUCTURE §5 / D-029). 7.1 publishes no
    # cross-module events (masters + pricing drive no effects; orders in 7.2 will).
    app.include_router(sales_router)
    # Manufacturing module (PLAN 8): PP master data (work centres, multi-level versioned BOMs,
    # routings) at /api/v1/manufacturing. Mounted after sales, the D-011 handler-registration
    # order; manufacturing reads finance/queries + inventory/queries downward (STRUCTURE §5 /
    # D-029). 8.1 publishes no cross-module events (masters drive no effects; production orders in
    # 8.2 will).
    app.include_router(manufacturing_router)
    # Quality module (PLAN 9): inspection lots at /api/v1/quality. Mounted after manufacturing, the
    # D-011 handler-registration order; quality SUBSCRIBES to procurement's GoodsReceiptPosted to
    # create inspection lots and reads inventory/queries downward (STRUCTURE §5 / D-029 / D-050). A
    # reject disposition publishes InspectionDispositioned → inventory moves the rejected stock.
    app.include_router(quality_router)
    # Maintenance module (PLAN 9.2): equipment + corrective/preventive orders + interval plans at
    # /api/v1/maintenance. Mounted after quality, the D-011 module import order; maintenance reads
    # finance/queries downward for an equipment's optional cost centre (STRUCTURE §5 / D-029 /
    # D-051). It publishes/subscribes to NO cross-module event in v1 — a completed order records its
    # cost on the order row (record-only, no GL posting, D-051).
    app.include_router(maintenance_router)
    # HR module (PLAN 10.1): employees (masked compensation/PII), departments, positions, org chart
    # at /api/v1/hr. Mounted after maintenance, the D-011 module import order; hr reads
    # finance/queries downward for a department's optional cost centre and probes core_users for an
    # employee's optional login (STRUCTURE §5 / D-029 / D-052). It is the FIRST real use of the
    # D-009
    # field-masking serializer (compensation/PII behind hr.employee.read_compensation). PLAN 10.4
    # adds payroll: HR PUBLISHES its first cross-module event (PayrollPosted) and finance posts the
    # consolidated payroll journal through the bus (D-055).
    app.include_router(hr_router)
    # Projects module (PLAN 11.1): projects + a WBS-element tree as COSTING OBJECTS + the project
    # cost report at /api/v1/projects. Mounted after hr, the D-011 module import order; projects is
    # the TOP of the dependency order — it reads finance/queries (cost-centre existence +
    # costs_by_project_dimension, the journal projection of actuals by the opaque WBS dimension),
    # hr/queries (approved hours by WBS), and sales/queries (customer existence) DOWNWARD (STRUCTURE
    # §5 / D-029 / D-056). It publishes/subscribes to NO cross-module event — projects is masters +
    # a READ report; "posting time/purchases to a WBS" means a journal line / timesheet tags the WBS
    # id as its opaque project dimension, projects posts nothing itself (D-056).
    app.include_router(projects_router)
    # CRM module (PLAN 12.1): leads → opportunities kanban + activities + convert-to-customer+quote
    # at
    # /api/v1/crm. Mounted after projects, the D-011 module import order; CRM is the TOP of the
    # dependency order — it reads finance/queries (currency existence), hr/queries (owner-employee
    # existence), inventory/queries (opportunity-line item existence + base UoM), and sales/queries
    # (existing-customer existence) DOWNWARD (STRUCTURE §5 / D-029 / D-057). The convert action
    # PUBLISHES OpportunityConverted and SALES' handler creates the customer + quote (CRM never
    # imports
    # sales/service); SALES imports crm/events declaratively (events-only, no cycle, D-057).
    app.include_router(crm_router)
    # Reporting module (PLAN 13.1): the role-based KPI dashboard at /api/v1/reporting. Mounted last,
    # the TOP of the dependency order — it is a READ-ONLY KPI aggregator that imports ONLY other
    # modules' queries DOWNWARD (finance/inventory/sales/procurement) for cash / AR-AP-aging /
    # inventory-value / open-orders / OTD / WIP, never their service/models, owns no tables, and
    # publishes/subscribes to NO cross-module event (D-058 / D-021 / STRUCTURE §5). finance,
    # inventory, sales, procurement are older and import nothing from reporting — one-way, no cycle.
    app.include_router(reporting_router)
    # Hospitality module (PLAN 19): restaurant menu availability, order tickets and background
    # ingredient depletion at /api/v1/hospitality. Mounted after reporting, the D-011 module import
    # order; hospitality reads inventory/queries and the manufacturing BOM engine DOWNWARD (recipes
    # ARE BOMs — no new item entity) and posts stock through the bus, never their services
    # (STRUCTURE §5). Task 6 fills the staff routes; the mount is already here because it is what
    # imports constants.py, and constants.py is where the D-009 permission keys register.
    app.include_router(hospitality_router)
    # ...and its WEBSITE-facing half on the same prefix but a separate router, because the caller is
    # a different kind of principal: a D-069 machine credential belonging to the property's own
    # site, not a member of staff. Split so the two surfaces can carry different cache policies and
    # so a website route can never inherit a staff route's guard by accident. Mounted AFTER the
    # staff router, which owns the more specific /menu/{item_id}/availability and /menu/at-risk.
    app.include_router(hospitality_website_router)
    # Phase 21's reservation surface, sibling router files for the same reason ap_router.py is one
    # (D-030/D-031): a second document family in a module whose router.py and website_router.py are
    # already near the size cap. Split staff/website by PRINCIPAL exactly as the two above are. The
    # website half runs under its own hospitality.reservation.book scope — narrower than the
    # menu/order key the site already holds, because the staff BOOK is every guest's name and phone
    # number for the night (D-069/D-070).
    app.include_router(hospitality_reservation_website_router)
    # Industry module (PLAN 14.1): the INDUSTRY CONFIGURATION LAYER at /api/v1/industry — the YAML
    # template catalog + the idempotent apply endpoint (D-060). Mounted last; it imports core +
    # admin (it applies to a tenant + writes settings) and PUBLISHES IndustryTemplateApplying for
    # the finance/inventory/procurement provisioning handlers — it never imports their services
    # (STRUCTURE §5). finance/inventory/procurement import industry/events (declarative) only.
    app.include_router(industry_router)
    # Onboarding wizard (PLAN 14.2 / D-061): POST /api/v1/onboarding/tenants provisions a WHOLE
    # tenant (tenant + first admin user + industry template) in one transaction. It lives in the
    # industry module (orchestrates admin.service + the loader) and is guarded by the platform
    # permission onboarding.tenant.create — a system action, not a tenant-admin one.
    app.include_router(onboarding_router)
    # Admin module (PLAN 14.3): the tenant-admin surface at /api/v1/admin — user/role management,
    # the audit viewer, and the number-sequence viewer, all over EXISTING core tables (no new
    # table/migration). Mounted last; it imports core + its own service/queries ONLY (STRUCTURE
    # §5) — it does NOT import finance, so exchange rates + tax codes stay on the finance router
    # (/api/v1/finance/exchange-rates, /tax-codes), cross-linked from docs/modules/admin.md.
    app.include_router(admin_router)


def register_event_handlers() -> None:
    """Register the cross-module domain-event handlers (D-011), in the deterministic module order.

    Called from ``create_app`` (the registration seam) and available to seed/CLI flows that build
    the
    bus without the HTTP app. IDEMPOTENT and re-runnable: each handler is (re)subscribed only if not
    already present for its key, so building several apps in one process — or re-registering after
    the
    test harness's ``clear_subscriptions`` reset (D-025) — yields exactly one subscription per
    handler, never a duplicate that would double-post."""
    from app.core.events import handlers_for, subscribe
    from app.modules.crm.events import OpportunityConverted
    from app.modules.finance.handlers import (
        create_bill_for_match,
        create_credit_note_for_return,
        create_invoice_for_billing,
        create_payroll_journal,
        post_production_variance,
        post_stock_valuation_journal,
        provision_finance_for_template,
    )
    from app.modules.hospitality.events import (
        RestaurantOrderFired,
        TicketIngredientsConsumed,
    )
    from app.modules.hospitality.handlers import submit_ticket_depletion
    from app.modules.hr.events import PayrollPosted
    from app.modules.industry.events import IndustryTemplateApplying
    from app.modules.inventory.events import StockValued
    from app.modules.inventory.handlers import (
        disposition_rejected_stock,
        issue_delivery_moves,
        issue_production_components,
        issue_ticket_ingredients,
        provision_inventory_for_template,
        receive_finished_order_move,
        receive_goods_receipt_moves,
        receive_return_moves,
    )
    from app.modules.manufacturing.events import (
        ComponentsIssued,
        OrderFinished,
        PlannedBuyConverted,
    )
    from app.modules.procurement.events import GoodsReceiptPosted, InvoiceMatched
    from app.modules.procurement.handlers import (
        create_requisition_for_planned_buy,
        provision_procurement_for_template,
    )
    from app.modules.quality.events import InspectionDispositioned
    from app.modules.quality.handlers import create_inspection_lots_for_receipt
    from app.modules.sales.events import (
        BillingInvoiced,
        DeliveryShipped,
        ReturnCredited,
        ReturnReceived,
    )
    from app.modules.sales.handlers import create_customer_and_quote_for_conversion

    if post_stock_valuation_journal not in handlers_for(StockValued.key):
        subscribe(StockValued.key, post_stock_valuation_journal)
    # Procurement goods-receipt → inventory stock-move bridge (PLAN 6.3, D-041): inventory's
    # handler creates the RECEIPT moves (Cr GR-IR) when a GR posts, which in turn publish
    # StockValued for the finance handler above — a two-hop same-transaction chain
    # (procurement → inventory → finance).
    if receive_goods_receipt_moves not in handlers_for(GoodsReceiptPosted.key):
        subscribe(GoodsReceiptPosted.key, receive_goods_receipt_moves)
    # Sales delivery → inventory stock-move bridge (PLAN 7.3, D-045): the OUTBOUND twin of the GR
    # bridge — inventory's handler creates the ISSUE moves (Dr COGS / Cr Inventory, COGS the default
    # issue offset — no override) when a delivery posts, which in turn publish StockValued for the
    # finance handler above — the same two-hop same-transaction chain (sales → inventory → finance).
    if issue_delivery_moves not in handlers_for(DeliveryShipped.key):
        subscribe(DeliveryShipped.key, issue_delivery_moves)
    # Procurement invoice-match → finance AP-bill bridge (PLAN 6.4, D-042): finance's handler
    # creates + posts the matched vendor bill (Dr GR/IR + PPV / Cr AP) when a match posts, clearing
    # the GR/IR account the goods receipt credited — closing the procure-to-pay loop. Procurement
    # publishes; finance handles its own bill posting (STRUCTURE §5).
    if create_bill_for_match not in handlers_for(InvoiceMatched.key):
        subscribe(InvoiceMatched.key, create_bill_for_match)
    # Sales billing → finance AR-invoice bridge (PLAN 7.4, D-046): the MIRROR of the invoice-match →
    # AP-bill bridge, sign-flipped — finance's handler creates + posts the AR customer invoice (Dr
    # AR
    # control / Cr revenue + tax) when a billing posts. Sales publishes; finance handles its own
    # invoice posting (STRUCTURE §5).
    if create_invoice_for_billing not in handlers_for(BillingInvoiced.key):
        subscribe(BillingInvoiced.key, create_invoice_for_billing)
    # Sales return → inventory RECEIPT bridge (PLAN 7.4, D-046): inventory's handler receives the
    # goods back (Dr Inventory / Cr COGS via the COGS-offset override — reversing the delivery's
    # issue) when a return posts, which publishes StockValued for the finance COGS handler above.
    if receive_return_moves not in handlers_for(ReturnReceived.key):
        subscribe(ReturnReceived.key, receive_return_moves)
    # Sales return → finance AR-credit-note bridge (PLAN 7.4, D-046): finance's handler creates +
    # posts the AR credit note (Dr revenue / Cr AR + reverse tax — reversing the billing) when a
    # return posts. The second leg of an atomic return post (the first is the stock receipt above).
    if create_credit_note_for_return not in handlers_for(ReturnCredited.key):
        subscribe(ReturnCredited.key, create_credit_note_for_return)
    # Manufacturing production-order → inventory stock-move bridges (PLAN 8.2, D-048), the
    # manufacturing↔inventory↔finance seam. A component ISSUE posts Dr WIP / Cr Inventory (the
    # valuation-offset OVERRIDE to the WIP account — the 6.3 GR/IR-override pattern applied to an
    # ISSUE) and a finished RECEIPT posts Dr Inventory / Cr WIP, both via inventory's handlers
    # creating the moves which in turn publish StockValued for the finance handler above — the same
    # two-hop same-transaction chain (manufacturing → inventory → finance). WIP nets to zero per
    # fully-issued + finished order; the variance flush is posted by manufacturing's finish flow.
    if issue_production_components not in handlers_for(ComponentsIssued.key):
        subscribe(ComponentsIssued.key, issue_production_components)
    # OrderFinished has TWO same-transaction subscribers: inventory's handler creates the finished
    # RECEIPT move (Dr Inventory / Cr WIP) and finance's handler posts the residual WIP variance (so
    # WIP nets to zero). Both drain in the finish's uow; either failure rolls the whole finish back.
    if receive_finished_order_move not in handlers_for(OrderFinished.key):
        subscribe(OrderFinished.key, receive_finished_order_move)
    if post_production_variance not in handlers_for(OrderFinished.key):
        subscribe(OrderFinished.key, post_production_variance)
    # Manufacturing planned-BUY → procurement DRAFT-requisition bridge (PLAN 8.3, D-049): a planned
    # BUY order's conversion publishes PlannedBuyConverted and procurement's handler creates the
    # requisition in the SAME transaction, linking the MRP run document → 'planned_to' → requisition
    # (the §5-clean planned-BUY → requisition mechanism — manufacturing never imports procurement
    # service, the billing → AR-invoice precedent).
    if create_requisition_for_planned_buy not in handlers_for(PlannedBuyConverted.key):
        subscribe(PlannedBuyConverted.key, create_requisition_for_planned_buy)
    # GoodsReceiptPosted has TWO same-transaction subscribers (PLAN 9.1, D-050): inventory's
    # receive_goods_receipt_moves (registered above) creates the RECEIPT moves, then quality's
    # create_inspection_lots_for_receipt creates an OPEN inspection lot per requires_inspection
    # line.
    # Quality is subscribed AFTER inventory (registration order = dispatch order, D-011) so the
    # lot/serial master instance the receipt creates already exists when quality resolves the GR
    # line's code to a traceability id.
    if create_inspection_lots_for_receipt not in handlers_for(GoodsReceiptPosted.key):
        subscribe(GoodsReceiptPosted.key, create_inspection_lots_for_receipt)
    # Quality reject-disposition → inventory stock-move bridge (PLAN 9.1, D-050): a REJECT usage
    # decision publishes InspectionDispositioned and inventory's handler moves the rejected stock
    # (SCRAP = an ADJUSTMENT-out write-off → Dr inventory-adjustment / Cr Inventory; BLOCK = a
    # value-neutral TRANSFER to the blocked bin) in the SAME transaction. Quality publishes;
    # inventory handles its own move (STRUCTURE §5). An ACCEPT publishes nothing — accepted stock is
    # already received and usable.
    if disposition_rejected_stock not in handlers_for(InspectionDispositioned.key):
        subscribe(InspectionDispositioned.key, disposition_rejected_stock)
    # HR payroll → finance consolidated-journal bridge (PLAN 10.4, D-055), HR's FIRST cross-module
    # event: a payroll-run post publishes PayrollPosted and finance's create_payroll_journal posts
    # the consolidated journal (Dr salary-expense by cost centre / Cr payroll-tax-payable / Cr
    # wages-payable — balanced because gross = tax + net) in the SAME transaction, linking the run
    # document → 'posts' → journal. HR publishes; finance handles its own journal posting (HR never
    # imports finance/service — STRUCTURE §5), the match → AP-bill / billing → AR-invoice precedent.
    if create_payroll_journal not in handlers_for(PayrollPosted.key):
        subscribe(PayrollPosted.key, create_payroll_journal)
    # CRM opportunity-convert → sales customer + quote bridge (PLAN 12.1, D-057), CRM's FIRST (and
    # only) cross-module event: a convert publishes OpportunityConverted and SALES'
    # create_customer_and_quote_for_conversion creates the customer (if the opportunity is not
    # already
    # linked to one) + the quote through SALES' OWN service in the SAME transaction, linking the
    # opportunity document → 'converted_to_quote' → quote document. CRM publishes; SALES handles its
    # own customer/quote creation (CRM never imports sales/service — STRUCTURE §5), the billing →
    # AR-invoice / planned-buy → requisition precedent with the roles flipped. SALES imports
    # crm/events
    # declaratively (events-only) — one-directional, no cycle (D-057).
    if create_customer_and_quote_for_conversion not in handlers_for(OpportunityConverted.key):
        subscribe(OpportunityConverted.key, create_customer_and_quote_for_conversion)
    # Industry template-apply → per-module provisioning bridges (PLAN 14.1, D-060): the industry
    # loader publishes IndustryTemplateApplying carrying the validated template, and the THREE
    # owning modules each create their slice IDEMPOTENTLY in the same transaction — finance
    # (currencies + COA + tax codes), inventory (UoMs + item categories), procurement (approval
    # presets). Industry never imports their services (STRUCTURE §5); it applies the core/admin
    # slices (custom-field defs, numbering sequences, terminology + module-toggle TenantSettings)
    # directly. Registration order = dispatch order: finance first (the COA other slices
    # conceptually sit on), then inventory, then procurement — the three slices are independent.
    if provision_finance_for_template not in handlers_for(IndustryTemplateApplying.key):
        subscribe(IndustryTemplateApplying.key, provision_finance_for_template)
    if provision_inventory_for_template not in handlers_for(IndustryTemplateApplying.key):
        subscribe(IndustryTemplateApplying.key, provision_inventory_for_template)
    if provision_procurement_for_template not in handlers_for(IndustryTemplateApplying.key):
        subscribe(IndustryTemplateApplying.key, provision_procurement_for_template)
    # Restaurant fire → background ingredient depletion (PLAN 19, spec Q4), a TWO-HOP chain whose
    # hops are in DIFFERENT transactions — the only one in Atlas, and the whole point of the phase.
    # Hop 1: firing a ticket publishes RestaurantOrderFired and hospitality's own
    # submit_ticket_depletion explodes the recipes and submits the PENDING job row in the FIRE's
    # transaction (so a D-013 replay returns the same job id). Hop 2: the job runner executes
    # deplete_ticket_job in its OWN uow, which publishes TicketIngredientsConsumed for inventory's
    # issue_ticket_ingredients to turn into ISSUE moves — which publish StockValued for the COGS
    # handler registered at the top of this function, exactly as any other goods issue does.
    # Synchronous depletion is what Q4 measured as an HTTP 500 at the guest's table
    # (MAX_DISPATCHES_PER_UOW counts handler invocations and a 56-line ticket exceeds it) and as a
    # phantom stock-out refusing a payment; hospitality never imports inventory's service
    # (STRUCTURE §5), so both hops go through the bus.
    if submit_ticket_depletion not in handlers_for(RestaurantOrderFired.key):
        subscribe(RestaurantOrderFired.key, submit_ticket_depletion)
    if issue_ticket_ingredients not in handlers_for(TicketIngredientsConsumed.key):
        subscribe(TicketIngredientsConsumed.key, issue_ticket_ingredients)
