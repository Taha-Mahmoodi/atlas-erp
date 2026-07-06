"""Demo-data seed for Atlas ERP — bootstraps the `acme` tenant + superuser, then populates
every module via the HTTP API.

Opt-in: does nothing unless ATLAS_SEED_DEMO is truthy. Refuses in prod (ATLAS_ENV=prod)
unless ATLAS_SEED_DEMO=force — the demo superuser has a public, hardcoded password, so it
must never seed a real production database by accident.

Run (backend already serving on :8000):
    ATLAS_SEED_DEMO=1 ATLAS_DATABASE_URL="sqlite+aiosqlite:///./atlas_local.db" \
    ATLAS_ENV=dev ATLAS_JWT_SECRET="local-dev-secret" uv run python seed.py

Idempotent: the tenant/user/role bootstrap is get-or-create; masters get-or-create by
unique code; transaction flows run only when their list endpoint is empty.
"""

import asyncio
import os
import sys
import uuid

import httpx

BASE = os.environ.get("ATLAS_API", "http://localhost:8000/api/v1")
TENANT, EMAIL, PASSWORD = "acme", "owner@acme.test", "correct-horse-battery"
TODAY = "2026-07-06"


def _seed_enabled() -> bool:
    """Guard: opt-in via ATLAS_SEED_DEMO, and never seed a prod DB with the public
    demo superuser unless explicitly forced (ATLAS_SEED_DEMO=force)."""
    flag = os.environ.get("ATLAS_SEED_DEMO", "").strip().lower()
    if flag in ("", "0", "false", "no"):
        print("seed: ATLAS_SEED_DEMO not set — skipping demo seed.")
        return False
    from app.core.config import get_settings

    if get_settings().env == "prod" and flag != "force":
        print(
            "seed: refusing to seed demo data into a prod database "
            "(set ATLAS_SEED_DEMO=force to override).",
            file=sys.stderr,
        )
        return False
    return True


async def bootstrap() -> None:
    """Idempotently create the acme tenant, the demo superuser, and a Superuser role
    holding the entire permission catalog. DB-direct (no register endpoint exists)."""
    from sqlalchemy import select

    import app.core.bootstrap  # noqa: F401 — side effect: registers every module's permission keys
    from app.core.db import build_session_factory, engine
    from app.core.models import Role, User, UserRole
    from app.core.rbac import catalog_keys, sync_permission_catalog
    from app.core.tenancy import system_context
    from app.modules.admin.models import Tenant
    from app.modules.admin.service import (
        assign_role,
        create_role,
        provision_tenant,
        provision_user,
    )

    async with build_session_factory(engine)() as db:
        with system_context():
            tenant = (
                await db.execute(select(Tenant).where(Tenant.slug == TENANT))
            ).scalar_one_or_none()
        if tenant is None:
            tenant = await provision_tenant(db, slug=TENANT, name=TENANT.title())

        with system_context():
            user = (
                await db.execute(
                    select(User).where(User.tenant_id == tenant.id, User.email == EMAIL)
                )
            ).scalar_one_or_none()
        if user is None:
            user = await provision_user(db, tenant.id, email=EMAIL, password=PASSWORD)

        with system_context():
            await sync_permission_catalog(db)
            role = (
                await db.execute(
                    select(Role).where(Role.tenant_id == tenant.id, Role.name == "Superuser")
                )
            ).scalar_one_or_none()
        if role is None:
            role = await create_role(
                db, tenant.id, "Superuser", sorted(catalog_keys()), is_system=True
            )

        with system_context():
            has_role = (
                await db.execute(
                    select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
                )
            ).scalar_one_or_none()
        if has_role is None:
            await assign_role(db, tenant.id, user.id, role.id, token_version=user.token_version)
        await db.commit()
    print(f"seed: bootstrap ok — tenant={TENANT} user={EMAIL} role=Superuser")


client = httpx.Client(base_url=BASE, timeout=30.0)
counts: dict[str, int] = {}


def login() -> None:
    r = client.post(
        "/auth/login", json={"tenant_slug": TENANT, "email": EMAIL, "password": PASSWORD}
    )
    r.raise_for_status()
    client.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


def get(path: str, **params):
    r = client.get(path, params=params)
    r.raise_for_status()
    return r.json()


def items(path: str) -> list:
    data = get(path, limit=200)
    return data["items"] if isinstance(data, dict) and "items" in data else data


def post(path: str, body=None, ok=(200, 201)):
    """POST; return json on success, None on a tolerated duplicate/validation clash.

    Sends a fresh Idempotency-Key — transactional endpoints require it. Re-run safety
    comes from the empty()/get_or_create guards, not from replaying the same key.
    """
    r = client.post(
        path, json=body if body is not None else {}, headers={"Idempotency-Key": uuid.uuid4().hex}
    )
    if r.status_code in ok:
        return r.json() if r.text else {}
    # tolerate idempotency clashes (duplicate code, already-in-state, etc.)
    if r.status_code in (400, 409, 422):
        return None
    raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:300]}")


def patch(path: str, body: dict):
    r = client.patch(path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    return r.json() if r.status_code < 300 else None


def put(path: str, body: dict):
    r = client.put(path, json=body, headers={"Idempotency-Key": uuid.uuid4().hex})
    return r.json() if r.status_code < 300 else None


def get_or_create(path: str, key: str, body: dict) -> dict:
    """REST resource where list-path == create-path and `key` is unique. Returns the row."""
    for it in items(path):
        if it.get(key) == body.get(key):
            return it
    created = post(path, body)
    if created:
        return created
    for it in items(path):  # created concurrently / duplicate — re-fetch
        if it.get(key) == body.get(key):
            return it
    raise RuntimeError(f"could not get_or_create {path} {body.get(key)}")


def empty(path: str) -> bool:
    return len(items(path)) == 0


# ── Finance ──────────────────────────────────────────────────────────────────
def seed_finance() -> dict:
    ctx = {}
    get_or_create(
        "/finance/currencies", "code", {"code": "USD", "name": "US Dollar", "is_functional": True}
    )
    get_or_create("/finance/currencies", "code", {"code": "EUR", "name": "Euro"})
    ctx["currency"] = "USD"

    get_or_create(
        "/finance/tax-codes",
        "code",
        {"code": "STD", "name": "Standard VAT 10%", "rate_percent": "10", "jurisdiction": "US"},
    )
    get_or_create(
        "/finance/tax-codes", "code", {"code": "ZERO", "name": "Zero Rated", "rate_percent": "0"}
    )

    grp = get_or_create("/finance/account-groups", "code", {"code": "1000", "name": "Assets"})
    # small chart of accounts
    coa = [
        ("1000", "Cash", "ASSET", "OPERATING", True),
        ("1100", "Accounts Receivable", "ASSET", None, False),
        ("1200", "Inventory", "ASSET", None, False),
        ("2000", "Accounts Payable", "LIABILITY", None, False),
        ("2100", "GR/IR Clearing", "LIABILITY", None, False),
        ("3000", "Share Capital", "EQUITY", None, False),
        ("4000", "Sales Revenue", "REVENUE", None, False),
        ("5000", "Cost of Goods Sold", "EXPENSE", None, False),
        ("6000", "Operating Expenses", "EXPENSE", None, False),
    ]
    accts = {}
    for code, name, atype, cf, cash in coa:
        body = {
            "code": code,
            "name": name,
            "account_type": atype,
            "account_group_id": grp["id"],
            "is_cash_equivalent": cash,
        }
        if cf:
            body["cash_flow_category"] = cf
        accts[code] = get_or_create("/finance/accounts", "code", body)
    ctx["accounts"] = {k: v["id"] for k, v in accts.items()}

    # posting defaults so sales-billing / goods-receipt / vendor-bill postings resolve GL accounts
    for purpose, code in [
        ("ar_control", "1100"),
        ("sales_revenue", "4000"),
        ("ap_control", "2000"),
        ("gr_ir_clearing", "2100"),
    ]:
        put("/finance/posting-defaults", {"purpose": purpose, "account_id": accts[code]["id"]})

    fy = get_or_create(
        "/finance/fiscal-years",
        "code",
        {"code": "FY2026", "name": "Fiscal Year 2026", "start_date": "2026-01-01"},
    )
    # open the period containing TODAY (2026-07 -> period 7)
    for p in items(f"/finance/fiscal-periods?fiscal_year_id={fy['id']}"):
        if p["start_date"] <= TODAY <= p["end_date"] and p["status"] != "OPEN":
            post(f"/finance/fiscal-periods/{p['id']}/open")

    cc = get_or_create("/finance/cost-centers", "code", {"code": "CC-OPS", "name": "Operations"})
    get_or_create(
        "/finance/cost-centers", "code", {"code": "CC-SALES", "name": "Sales & Marketing"}
    )
    pc = get_or_create(
        "/finance/profit-centers", "code", {"code": "PC-MAIN", "name": "Main Business"}
    )
    ctx["cost_center"] = cc["id"]
    ctx["profit_center"] = pc["id"]

    # journal entry (balanced) + post — only if none exist yet
    if empty("/finance/journal-entries"):
        je = post(
            "/finance/journal-entries",
            {
                "posting_date": TODAY,
                "currency_code": "USD",
                "description": "Opening capital injection",
                "document_type": "JOURNAL",
                "lines": [
                    {
                        "account_id": accts["1000"]["id"],
                        "description": "Cash in",
                        "transaction_debit_amount": "50000",
                        "transaction_credit_amount": "0",
                        "cost_center_id": cc["id"],
                        "profit_center_id": pc["id"],
                    },
                    {
                        "account_id": accts["3000"]["id"],
                        "description": "Share capital",
                        "transaction_debit_amount": "0",
                        "transaction_credit_amount": "50000",
                    },
                ],
            },
        )
        if je:
            post(f"/finance/journal-entries/{je['id']}/post")
    return ctx


# ── Inventory ────────────────────────────────────────────────────────────────
def seed_inventory(fin: dict) -> dict:
    ctx = {}
    ea = get_or_create("/inventory/uoms", "code", {"code": "EA", "name": "Each"})
    get_or_create("/inventory/uoms", "code", {"code": "KG", "name": "Kilogram"})
    get_or_create("/inventory/uoms", "code", {"code": "HR", "name": "Hour"})
    ctx["uom"] = ea["id"]

    cat = get_or_create(
        "/inventory/item-categories", "code", {"code": "FG", "name": "Finished Goods"}
    )
    # wire the three valuation accounts (required before any stock move can be valued)
    patch(
        f"/inventory/item-categories/{cat['id']}",
        {
            "inventory_account_id": fin["accounts"]["1200"],
            "cogs_account_id": fin["accounts"]["5000"],
            "price_difference_account_id": fin["accounts"]["6000"],
        },
    )
    get_or_create("/inventory/item-categories", "code", {"code": "RM", "name": "Raw Materials"})

    wh = get_or_create("/inventory/warehouses", "code", {"code": "WH1", "name": "Main Warehouse"})
    ctx["warehouse"] = wh["id"]
    bin_ = get_or_create(
        "/inventory/bins",
        "code",
        {"warehouse_id": wh["id"], "code": "A-01", "name": "Aisle A Bin 01", "is_default": True},
    )
    ctx["bin"] = bin_["id"]

    specs = [
        ("ITM-WIDGET", "Blue Widget", "STOCKED"),
        ("ITM-GADGET", "Red Gadget", "STOCKED"),
        ("ITM-BOLT", "Steel Bolt M6", "STOCKED"),
        ("ITM-CASING", "Plastic Casing", "STOCKED"),
        ("ITM-INSTALL", "Installation Service", "SERVICE"),
    ]
    it_ids = {}
    for code, name, itype in specs:
        body = {
            "item_code": code,
            "name": name,
            "item_type": itype,
            "category_id": cat["id"],
            "base_uom_id": ea["id"],
        }
        it_ids[code] = get_or_create("/inventory/items", "item_code", body)["id"]
    ctx["items"] = it_ids

    # guarantee on-hand for the widget (sold later) via an adjustment move
    if empty("/inventory/stock-moves"):
        post(
            "/inventory/stock-moves",
            {
                "move_type": "ADJUSTMENT",
                "item_id": it_ids["ITM-WIDGET"],
                "quantity": "200",
                "to_bin_id": bin_["id"],
                "move_date": TODAY,
                "unit_cost": "12.50",
                "reference": "Opening stock",
            },
        )
    return ctx


# ── Procurement ──────────────────────────────────────────────────────────────
def seed_procurement(fin: dict, inv: dict) -> dict:
    ctx = {}
    vendors = [
        ("V-ACME-SUP", "Acme Supplies Co"),
        ("V-GLOBAL", "Global Parts Ltd"),
        ("V-FAST", "FastShip Logistics"),
    ]
    vids = {
        c: get_or_create(
            "/procurement/vendors",
            "vendor_code",
            {
                "vendor_code": c,
                "name": n,
                "default_currency_code": "USD",
                "email": f"sales@{c.lower()}.test",
            },
        )["id"]
        for c, n in vendors
    }
    ctx["vendors"] = vids

    # register the purchased item as an approved source for the vendor (required by convert-to-po)
    post(
        f"/procurement/vendors/{vids['V-ACME-SUP']}/approved-items",
        {"item_id": inv["items"]["ITM-BOLT"]},
    )

    # requisition -> submit (auto-approves) -> convert-to-po -> send -> goods-receipt -> post
    if empty("/procurement/purchase-orders"):
        req = post(
            "/procurement/requisitions",
            {
                "needed_by_date": TODAY,
                "notes": "Restock raw materials",
                "lines": [
                    {
                        "item_id": inv["items"]["ITM-BOLT"],
                        "description": "Steel bolts",
                        "quantity": "500",
                        "uom_id": inv["uom"],
                        "estimated_unit_cost": "0.20",
                        "currency_code": "USD",
                    }
                ],
            },
        )
        po = None
        if req:
            post(
                f"/procurement/requisitions/{req['id']}/submit"
            )  # auto-approves (no approval rule)
            po = post(
                f"/procurement/requisitions/{req['id']}/convert-to-po",
                {"vendor_id": vids["V-ACME-SUP"], "order_date": TODAY, "expected_date": TODAY},
            )
        if not po:  # fallback: direct PO
            po = post(
                "/procurement/purchase-orders",
                {
                    "vendor_id": vids["V-ACME-SUP"],
                    "currency_code": "USD",
                    "order_date": TODAY,
                    "lines": [
                        {
                            "item_id": inv["items"]["ITM-BOLT"],
                            "quantity": "500",
                            "uom_id": inv["uom"],
                            "unit_cost": "0.20",
                        }
                    ],
                },
            )
        if po:
            post(f"/procurement/purchase-orders/{po['id']}/decision", {"decision": "APPROVED"})
            post(f"/procurement/purchase-orders/{po['id']}/send")
            detail = get(f"/procurement/purchase-orders/{po['id']}")
            po_lines = detail.get("lines", [])
            if po_lines:
                gr = post(
                    "/procurement/goods-receipts",
                    {
                        "purchase_order_id": po["id"],
                        "warehouse_id": inv["warehouse"],
                        "receipt_date": TODAY,
                        "lines": [
                            {
                                "purchase_order_line_id": po_lines[0]["id"],
                                "bin_id": inv["bin"],
                                "received_quantity": "500",
                                "requires_inspection": False,
                            }
                        ],
                    },
                )
                if gr:
                    post(f"/procurement/goods-receipts/{gr['id']}/post")
    return ctx


# ── Quality ──────────────────────────────────────────────────────────────────
def seed_quality(inv: dict, proc: dict) -> None:
    """Generate an inspection lot via an inspection-required goods receipt, then decide it."""
    vid = proc["vendors"]["V-GLOBAL"]
    post(f"/procurement/vendors/{vid}/approved-items", {"item_id": inv["items"]["ITM-CASING"]})
    if not empty("/quality/inspection-lots"):
        return
    po = post(
        "/procurement/purchase-orders",
        {
            "vendor_id": vid,
            "currency_code": "USD",
            "order_date": TODAY,
            "lines": [
                {
                    "item_id": inv["items"]["ITM-CASING"],
                    "quantity": "100",
                    "uom_id": inv["uom"],
                    "unit_cost": "1.50",
                }
            ],
        },
    )
    if not po:
        return
    post(f"/procurement/purchase-orders/{po['id']}/decision", {"decision": "APPROVED"})
    post(f"/procurement/purchase-orders/{po['id']}/send")
    lines = get(f"/procurement/purchase-orders/{po['id']}").get("lines", [])
    if not lines:
        return
    gr = post(
        "/procurement/goods-receipts",
        {
            "purchase_order_id": po["id"],
            "warehouse_id": inv["warehouse"],
            "receipt_date": TODAY,
            "lines": [
                {
                    "purchase_order_line_id": lines[0]["id"],
                    "bin_id": inv["bin"],
                    "received_quantity": "100",
                    "requires_inspection": True,
                }
            ],
        },
    )
    if gr:
        post(f"/procurement/goods-receipts/{gr['id']}/post")
    for lot in items("/quality/inspection-lots"):
        if lot.get("status") not in ("ACCEPTED", "REJECTED", "CANCELLED"):
            post(
                f"/quality/inspection-lots/{lot['id']}/decide",
                {"accepted_quantity": lot["quantity"], "rejected_quantity": "0"},
            )


# ── Sales ────────────────────────────────────────────────────────────────────
def seed_sales(fin: dict, inv: dict) -> dict:
    ctx = {}
    grp = get_or_create(
        "/sales/customer-groups", "code", {"code": "RETAIL", "name": "Retail Customers"}
    )
    get_or_create("/sales/customer-groups", "code", {"code": "WHOLESALE", "name": "Wholesale"})
    customers = [
        ("C-NORTH", "Northwind Traders"),
        ("C-CONTOSO", "Contoso Retail"),
        ("C-FABRIKAM", "Fabrikam Inc"),
    ]
    cids = {
        c: get_or_create(
            "/sales/customers",
            "customer_code",
            {
                "customer_code": c,
                "name": n,
                "default_currency_code": "USD",
                "customer_group_id": grp["id"],
                "credit_limit": "100000",
                "email": f"buyer@{c.lower()}.test",
            },
        )["id"]
        for c, n in customers
    }
    ctx["customers"] = cids

    pl = get_or_create(
        "/sales/price-lists",
        "code",
        {
            "code": "PL-STD",
            "name": "Standard Price List",
            "currency_code": "USD",
            "valid_from": "2026-01-01",
        },
    )
    if empty(f"/sales/price-lists/{pl['id']}/items"):
        post(
            f"/sales/price-lists/{pl['id']}/items",
            {"item_id": inv["items"]["ITM-WIDGET"], "unit_price": "25.00"},
        )
        post(
            f"/sales/price-lists/{pl['id']}/items",
            {"item_id": inv["items"]["ITM-GADGET"], "unit_price": "40.00"},
        )

    # quote -> send -> accept -> convert-to-order -> confirm -> delivery+post -> billing+post
    if empty("/sales/orders"):
        q = post(
            "/sales/quotes",
            {
                "customer_id": cids["C-NORTH"],
                "currency_code": "USD",
                "quote_date": TODAY,
                "valid_until": "2026-08-31",
                "notes": "Q3 widget order",
                "lines": [
                    {
                        "item_id": inv["items"]["ITM-WIDGET"],
                        "quantity": "50",
                        "uom_id": inv["uom"],
                        "unit_price": "25.00",
                    }
                ],
            },
        )
        order = None
        if q:
            post(f"/sales/quotes/{q['id']}/send")
            post(f"/sales/quotes/{q['id']}/accept")
            order = post(
                f"/sales/quotes/{q['id']}/convert-to-order",
                {"order_date": TODAY, "requested_date": TODAY},
            )
        if order:
            post(f"/sales/orders/{order['id']}/confirm")
            od = get(f"/sales/orders/{order['id']}")
            olines = od.get("lines", [])
            if olines:
                dl = post(
                    "/sales/deliveries",
                    {
                        "sales_order_id": order["id"],
                        "warehouse_id": inv["warehouse"],
                        "delivery_date": TODAY,
                        "lines": [
                            {
                                "sales_order_line_id": olines[0]["id"],
                                "bin_id": inv["bin"],
                                "quantity": "50",
                            }
                        ],
                    },
                )
                if dl:
                    post(f"/sales/deliveries/{dl['id']}/post")
                post(
                    "/sales/billings",
                    {
                        "sales_order_id": order["id"],
                        "billing_date": TODAY,
                        "bill_all_delivered": True,
                    },
                )

    # post any DRAFT deliveries/billings (also completes rows left unposted by earlier runs)
    for d in items("/sales/deliveries"):
        if d.get("status") == "DRAFT":
            post(f"/sales/deliveries/{d['id']}/post")
    for b in items("/sales/billings"):
        if b.get("status") == "DRAFT":
            post(f"/sales/billings/{b['id']}/post")
    return ctx


# ── Manufacturing ────────────────────────────────────────────────────────────
def seed_manufacturing(fin: dict, inv: dict) -> None:
    wc = get_or_create(
        "/manufacturing/work-centers",
        "code",
        {
            "code": "WC-ASSY",
            "name": "Assembly Line",
            "cost_center_id": fin["cost_center"],
            "capacity_hours_per_day": "8",
        },
    )
    get_or_create(
        "/manufacturing/work-centers",
        "code",
        {"code": "WC-PACK", "name": "Packaging", "capacity_hours_per_day": "8"},
    )

    if empty("/manufacturing/boms"):
        bom = post(
            "/manufacturing/boms",
            {
                "item_id": inv["items"]["ITM-GADGET"],
                "version": "v1",
                "name": "Red Gadget BOM",
                "base_quantity": "1",
                "uom_id": inv["uom"],
            },
        )
        if bom:
            post(
                f"/manufacturing/boms/{bom['id']}/components",
                {
                    "component_item_id": inv["items"]["ITM-BOLT"],
                    "quantity_per": "4",
                    "uom_id": inv["uom"],
                },
            )
            post(
                f"/manufacturing/boms/{bom['id']}/components",
                {
                    "component_item_id": inv["items"]["ITM-CASING"],
                    "quantity_per": "1",
                    "uom_id": inv["uom"],
                },
            )
            post(f"/manufacturing/boms/{bom['id']}/activate")

    routing_id = None
    if empty("/manufacturing/routings"):
        rt = post(
            "/manufacturing/routings",
            {"item_id": inv["items"]["ITM-GADGET"], "version": "v1", "name": "Red Gadget Routing"},
        )
        if rt:
            post(
                f"/manufacturing/routings/{rt['id']}/operations",
                {
                    "work_center_id": wc["id"],
                    "description": "Assemble",
                    "setup_time_minutes": "15",
                    "run_time_minutes_per_unit": "5",
                },
            )
            post(f"/manufacturing/routings/{rt['id']}/activate")
            routing_id = rt["id"]

    if empty("/manufacturing/production-orders"):
        boms = items("/manufacturing/boms")
        rts = items("/manufacturing/routings")
        po = post(
            "/manufacturing/production-orders",
            {
                "item_id": inv["items"]["ITM-GADGET"],
                "quantity": "20",
                "warehouse_id": inv["warehouse"],
                "bom_id": boms[0]["id"] if boms else None,
                "routing_id": (routing_id or (rts[0]["id"] if rts else None)),
                "planned_start_date": TODAY,
            },
        )
        if po:
            post(f"/manufacturing/production-orders/{po['id']}/release")


# ── Maintenance ──────────────────────────────────────────────────────────────
def seed_maintenance(fin: dict) -> None:
    eq = get_or_create(
        "/maintenance/equipment",
        "code",
        {
            "code": "EQ-CNC1",
            "name": "CNC Machine 1",
            "location": "Plant Floor",
            "manufacturer": "Haas",
            "cost_center_id": fin["cost_center"],
        },
    )
    get_or_create(
        "/maintenance/equipment",
        "code",
        {"code": "EQ-FORK1", "name": "Forklift 1", "location": "Warehouse"},
    )

    if empty("/maintenance/maintenance-plans"):
        plan = post(
            "/maintenance/maintenance-plans",
            {
                "code": "MP-CNC-MONTHLY",
                "name": "CNC Monthly Service",
                "equipment_id": eq["id"],
                "interval_value": 1,
                "interval_unit": "MONTHS",
                "task_description": "Lubricate & inspect",
                "start_date": TODAY,
                "estimated_cost": "250",
            },
        )
        if plan:
            post(f"/maintenance/maintenance-plans/{plan['id']}/activate")

    if empty("/maintenance/maintenance-orders"):
        post(
            "/maintenance/maintenance-orders",
            {
                "equipment_id": eq["id"],
                "description": "Replace worn spindle bearing",
                "scheduled_date": TODAY,
                "estimated_cost": "800",
            },
        )


# ── HR ───────────────────────────────────────────────────────────────────────
def seed_hr(fin: dict) -> dict:
    ctx = {}
    dept = get_or_create(
        "/hr/departments",
        "code",
        {"code": "D-OPS", "name": "Operations", "cost_center_id": fin["cost_center"]},
    )
    get_or_create("/hr/departments", "code", {"code": "D-SALES", "name": "Sales"})
    pos = get_or_create(
        "/hr/positions",
        "code",
        {"code": "P-TECH", "title": "Technician", "department_id": dept["id"]},
    )
    get_or_create(
        "/hr/positions", "code", {"code": "P-MGR", "title": "Manager", "department_id": dept["id"]}
    )

    emps = [
        ("E-1001", "Alice", "Johnson"),
        ("E-1002", "Bob", "Smith"),
        ("E-1003", "Carol", "Nguyen"),
    ]
    eids = {}
    for code, fn, ln in emps:
        eids[code] = get_or_create(
            "/hr/employees",
            "employee_code",
            {
                "employee_code": code,
                "first_name": fn,
                "last_name": ln,
                "email": f"{fn.lower()}@acme.test",
                "department_id": dept["id"],
                "position_id": pos["id"],
                "hire_date": "2025-01-15",
                "base_salary": "60000",
                "currency_code": "USD",
            },
        )["id"]
    ctx["employees"] = eids

    lt = get_or_create(
        "/hr/leave-types",
        "code",
        {"code": "LT-ANNUAL", "name": "Annual Leave", "accrual_amount": "1.75"},
    )
    if empty("/hr/leave-requests"):
        lr = post(
            "/hr/leave-requests",
            {
                "employee_id": eids["E-1001"],
                "leave_type_id": lt["id"],
                "start_date": "2026-07-20",
                "end_date": "2026-07-24",
                "days": "5",
                "reason": "Summer vacation",
            },
        )
        if lr:
            post(f"/hr/leave-requests/{lr['id']}/submit")

    if empty("/hr/timesheets"):
        ts = post(
            "/hr/timesheets",
            {
                "employee_id": eids["E-1002"],
                "period_start": "2026-06-29",
                "period_end": "2026-07-05",
                "notes": "Week 27",
            },
        )
        if ts:
            post(
                f"/hr/timesheets/{ts['id']}/time-entries",
                {
                    "entry_date": "2026-06-30",
                    "hours": "8",
                    "cost_center_id": fin["cost_center"],
                    "task_description": "Assembly work",
                    "is_billable": True,
                },
            )
            post(f"/hr/timesheets/{ts['id']}/submit")
    return ctx


# ── Projects ─────────────────────────────────────────────────────────────────
def seed_projects(fin: dict, sales: dict) -> None:
    cust = next(iter(sales.get("customers", {}).values()), None)
    proj = get_or_create(
        "/projects",
        "code",
        {
            "code": "PRJ-ERP",
            "name": "ERP Rollout",
            "status": "ACTIVE",
            "customer_id": cust,
            "cost_center_id": fin["cost_center"],
            "start_date": TODAY,
            "budget_amount": "150000",
        },
    )
    if empty(f"/projects/{proj['id']}/wbs-elements"):
        post(
            f"/projects/{proj['id']}/wbs-elements",
            {"code": "WBS-1", "name": "Discovery & Planning", "budget_amount": "40000"},
        )
        post(
            f"/projects/{proj['id']}/wbs-elements",
            {
                "code": "WBS-2",
                "name": "Implementation",
                "is_billable": True,
                "budget_amount": "110000",
            },
        )


# ── CRM ──────────────────────────────────────────────────────────────────────
def seed_crm(hr: dict) -> None:
    owner = next(iter(hr.get("employees", {}).values()), None)
    if empty("/crm/leads"):
        post(
            "/crm/leads",
            {
                "company_name": "Prospect Alpha LLC",
                "contact_name": "Dana White",
                "email": "dana@alpha.test",
                "source": "Website",
                "status": "NEW",
                "estimated_value": "25000",
                "currency_code": "USD",
                "owner_employee_id": owner,
            },
        )
        post(
            "/crm/leads",
            {
                "company_name": "Beta Industries",
                "contact_name": "Evan Lee",
                "source": "Referral",
                "estimated_value": "50000",
                "currency_code": "USD",
            },
        )
    if empty("/crm/opportunities"):
        post(
            "/crm/opportunities",
            {
                "name": "Beta Industries — Platform Deal",
                "company_name": "Beta Industries",
                "contact_name": "Evan Lee",
                "currency_code": "USD",
                "estimated_value": "50000",
                "probability_percent": "40",
                "expected_close_date": "2026-09-30",
                "owner_employee_id": owner,
            },
        )
    if empty("/crm/activities"):
        leads = items("/crm/leads")
        opps = items("/crm/opportunities")
        if opps:  # activity must reference exactly one lead or opportunity
            post(
                "/crm/activities",
                {
                    "activity_type": "CALL",
                    "subject": "Discovery call with Beta",
                    "status": "OPEN",
                    "due_date": TODAY,
                    "owner_employee_id": owner,
                    "opportunity_id": opps[0]["id"],
                },
            )
        if leads:
            post(
                "/crm/activities",
                {
                    "activity_type": "EMAIL",
                    "subject": "Send proposal to Alpha",
                    "status": "OPEN",
                    "lead_id": leads[0]["id"],
                },
            )


# ── Verify ───────────────────────────────────────────────────────────────────
VERIFY = {
    "finance/currencies": "Currencies",
    "finance/accounts": "Accounts",
    "finance/journal-entries": "Journal entries",
    "finance/cost-centers": "Cost centers",
    "inventory/items": "Items",
    "inventory/warehouses": "Warehouses",
    "inventory/stock-moves": "Stock moves",
    "procurement/vendors": "Vendors",
    "procurement/purchase-orders": "Purchase orders",
    "procurement/goods-receipts": "Goods receipts",
    "sales/customers": "Customers",
    "sales/quotes": "Quotes",
    "sales/orders": "Sales orders",
    "sales/deliveries": "Deliveries",
    "sales/billings": "Billings",
    "manufacturing/work-centers": "Work centers",
    "manufacturing/boms": "BOMs",
    "manufacturing/routings": "Routings",
    "manufacturing/production-orders": "Production orders",
    "quality/inspection-lots": "Inspection lots",
    "maintenance/equipment": "Equipment",
    "maintenance/maintenance-plans": "Maintenance plans",
    "maintenance/maintenance-orders": "Maintenance orders",
    "hr/departments": "Departments",
    "hr/employees": "Employees",
    "hr/leave-requests": "Leave requests",
    "hr/timesheets": "Timesheets",
    "projects": "Projects",
    "crm/leads": "Leads",
    "crm/opportunities": "Opportunities",
    "crm/activities": "Activities",
}


def main() -> None:
    if not _seed_enabled():
        return
    asyncio.run(bootstrap())
    login()
    fin = seed_finance()
    inv = seed_inventory(fin)
    proc = seed_procurement(fin, inv)
    seed_quality(inv, proc)
    sales = seed_sales(fin, inv)
    seed_manufacturing(fin, inv)
    seed_maintenance(fin)
    hr = seed_hr(fin)
    seed_projects(fin, sales)
    seed_crm(hr)

    print("\n=== SEED SUMMARY (row counts per list endpoint) ===")
    for path, label in VERIFY.items():
        try:
            n = len(items("/" + path))
        except Exception as e:  # noqa: BLE001
            n = f"ERR {e}"
        print(f"  {label:<20} {n}")


if __name__ == "__main__":
    main()
