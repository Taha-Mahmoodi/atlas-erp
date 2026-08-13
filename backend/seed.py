"""Demo-data seed for Atlas ERP (PLAN 16.1/16.2).

Two modes:

* Default: one demo tenant per industry template (manufacturing, retail,
  professional-services, healthcare, construction) plus the industry-agnostic `acme`
  baseline — each bootstrapped with a full-catalog superuser, its industry template
  applied, and ~3 months of interlinked transactions seeded through the HTTP API
  (procure-to-pay, order-to-cash, make-to-stock where enabled, HR/time/payroll,
  projects) so every report shows real data. Login: owner@<slug>.test / the shared
  demo password below.

* ``--volume``: a high-volume `volume` tenant per PERFORMANCE.md §5 — ≥100k journal
  lines, ≥50k stock moves, ≥10k sales orders, ≥5k items, 3 fiscal years — written with
  direct bulk DB inserts (no HTTP), finishing in minutes. Drives the tests/perf/ budgets.

Opt-in: does nothing unless ATLAS_SEED_DEMO is truthy. Refuses in prod (ATLAS_ENV=prod)
unless ATLAS_SEED_DEMO=force — the demo superuser has a public, hardcoded password, so it
must never seed a real production database by accident.

Run (backend already serving on :8000; --volume needs no server):
    ATLAS_SEED_DEMO=1 ATLAS_DATABASE_URL="sqlite+aiosqlite:///./atlas_local.db" \
    ATLAS_ENV=dev ATLAS_JWT_SECRET="local-dev-secret" uv run python seed.py [--volume]

Idempotent: tenant/user/role bootstrap and masters are get-or-create; transaction flows
run only when their list endpoint is empty; --volume skips a tenant that already has
journal entries.
"""

import asyncio
import os
import sys
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx

BASE = os.environ.get("ATLAS_API", "http://localhost:8000/api/v1")
PASSWORD = "correct-horse-battery"
TODAY = date(2026, 7, 6)
START = date(2026, 4, 6)  # ~3 months of history
OPENING = date(2026, 3, 30)  # opening stock lands just BEFORE the window so its valuation
# offset (price-difference) doesn't distort the 3-month P&L
WEEKS = [START + timedelta(days=7 * i) for i in range(13)]
MONTHS = [  # (first day, last day) of each fully-seeded month
    (date(2026, 4, 1), date(2026, 4, 30)),
    (date(2026, 5, 1), date(2026, 5, 31)),
    (date(2026, 6, 1), date(2026, 6, 30)),
]


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


# ── Tenant profiles ──────────────────────────────────────────────────────────
# One profile per industry template + the acme baseline. ``coa`` maps a ROLE the flows
# need to (code, name, type[, cash_flow, cash_equiv]); template-shipped accounts are
# found by code, missing ones are created. ``items`` = (code, name, type, category,
# sell_price, unit_cost); ``sell``/``make``/``buys`` index into it. ``flows`` mirrors the
# template's module toggles; ``stock`` False = a service business (no warehouse/moves —
# O2C runs quote→order→confirm + direct AR fee invoices, P2P runs direct AP bills).

def _acct(code, name, atype, cf=None, cash=False):
    return {"code": code, "name": name, "type": atype, "cf": cf, "cash": cash}


PROFILES = [
    {
        "slug": "acme",
        "template": None,
        "name": "Acme",
        "coa": {
            "cash": _acct("1000", "Cash", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Accounts Receivable", "ASSET"),
            "inv": _acct("1200", "Inventory", "ASSET"),
            "wip": _acct("1210", "Work In Progress", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "grir": _acct("2100", "GR/IR Clearing", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "paytax": _acct("2400", "Payroll Tax Payable", "LIABILITY"),
            "equity": _acct("3000", "Share Capital", "EQUITY"),
            "rev": _acct("4000", "Sales Revenue", "REVENUE"),
            "cogs": _acct("5000", "Cost of Goods Sold", "EXPENSE"),
            "prodvar": _acct("5100", "Production Variance", "EXPENSE"),
            "opex": _acct("6000", "Operating Expenses", "EXPENSE"),
            "salary": _acct("6100", "Salaries Expense", "EXPENSE"),
        },
        "pricediff": "opex",
        "categories": {"FG": "inv", "RM": "inv"},
        "items": [
            ("ITM-WIDGET", "Blue Widget", "STOCKED", "FG", "25.00", "12.50"),
            ("ITM-GADGET", "Red Gadget", "STOCKED", "FG", "40.00", "18.00"),
            ("ITM-BOLT", "Steel Bolt M6", "STOCKED", "RM", None, "0.20"),
            ("ITM-CASING", "Plastic Casing", "STOCKED", "RM", None, "1.50"),
            ("ITM-INSTALL", "Installation Service", "SERVICE", "FG", "90.00", None),
        ],
        "sell": 0,
        "make": 1,
        "buys": [2, 3],
        "vendors": [("V-ACME-SUP", "Acme Supplies Co"), ("V-GLOBAL", "Global Parts Ltd"),
                    ("V-FAST", "FastShip Logistics")],
        "customers": [("C-NORTH", "Northwind Traders"), ("C-CONTOSO", "Contoso Retail"),
                      ("C-FABRIKAM", "Fabrikam Inc")],
        "employees": [("E-1001", "Alice", "Johnson", "5000"), ("E-1002", "Bob", "Smith", "4500"),
                      ("E-1003", "Carol", "Nguyen", "6000")],
        "department": ("D-OPS", "Operations"),
        "projects": [("PRJ-ERP", "ERP Rollout", "150000"), ("PRJ-WEB", "Webshop Launch", "60000")],
        "flows": {"mfg": True, "quality": True, "maintenance": True, "projects": True,
                  "crm": True, "stock": True},
    },
    {
        "slug": "manufacturing",
        "template": "manufacturing",
        "name": "Vertex Manufacturing",
        "coa": {
            "cash": _acct("1000", "Cash", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Accounts Receivable", "ASSET"),
            "inv": _acct("1320", "Finished Goods Inventory", "ASSET"),
            "raw": _acct("1300", "Raw Materials Inventory", "ASSET"),
            "wip": _acct("1310", "Work In Progress", "ASSET"),
            "grir": _acct("1400", "GR/IR Clearing", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "paytax": _acct("2200", "Tax Payable", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "equity": _acct("3000", "Owner Equity", "EQUITY"),
            "rev": _acct("4000", "Product Sales Revenue", "REVENUE"),
            "cogs": _acct("5000", "Cost of Goods Sold", "EXPENSE"),
            "prodvar": _acct("5100", "Production Variance", "EXPENSE"),
            "pricediff_a": _acct("5200", "Inventory Price Difference", "EXPENSE"),
            "opex": _acct("6000", "Operating Expenses", "EXPENSE"),
            "salary": _acct("6100", "Salaries Expense", "EXPENSE"),
        },
        "pricediff": "pricediff_a",
        "categories": {"RAW": "raw", "FG": "inv"},
        "items": [
            ("PMP-100", "Centrifugal Pump PMP-100", "STOCKED", "FG", "1200.00", "700.00"),
            ("RM-HOUSING", "Cast Steel Housing", "STOCKED", "RAW", None, "180.00"),
            ("RM-SEAL", "Mechanical Seal Kit", "STOCKED", "RAW", None, "45.00"),
        ],
        "sell": 0,
        "make": 0,
        "buys": [1, 2],
        "vendors": [("V-CAST", "Precision Castings GmbH"), ("V-SEAL", "SealTech Industrial"),
                    ("V-FRT", "Interstate Freight")],
        "customers": [("C-MERID", "Meridian Equipment"), ("C-DELTA", "Delta Process Systems"),
                      ("C-NORD", "Nordwind Industrial")],
        "employees": [("E-2001", "Marta", "Kovacs", "4800"), ("E-2002", "Dev", "Patel", "4300"),
                      ("E-2003", "Lena", "Fischer", "6300")],
        "department": ("D-PROD", "Production"),
        "projects": [("PRJ-LINE2", "Assembly Line 2 Expansion", "250000")],
        "flows": {"mfg": True, "quality": True, "maintenance": True, "projects": True,
                  "crm": True, "stock": True},
    },
    {
        "slug": "retail",
        "template": "retail",
        "name": "Brightside Retail",
        "coa": {
            "cash": _acct("1000", "Cash Register", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Accounts Receivable", "ASSET"),
            "inv": _acct("1300", "Merchandise Inventory", "ASSET"),
            "grir": _acct("1400", "GR/IR Clearing", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "paytax": _acct("2200", "Sales Tax Payable", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "equity": _acct("3000", "Owner Equity", "EQUITY"),
            "rev": _acct("4000", "Merchandise Sales", "REVENUE"),
            "cogs": _acct("5000", "Cost of Goods Sold", "EXPENSE"),
            "pricediff_a": _acct("5200", "Inventory Shrinkage", "EXPENSE"),
            "opex": _acct("6000", "Operating Expenses", "EXPENSE"),
            "salary": _acct("6100", "Salaries Expense", "EXPENSE"),
        },
        "pricediff": "pricediff_a",
        "categories": {"MERCH": "inv"},
        "items": [
            ("SKU-ESP", "Espresso Beans 1kg", "STOCKED", "MERCH", "18.00", "9.50"),
            ("SKU-MUG", "Stoneware Mug", "STOCKED", "MERCH", "12.00", "4.20"),
            ("SKU-GRND", "Hand Coffee Grinder", "STOCKED", "MERCH", "65.00", "32.00"),
        ],
        "sell": 0,
        "make": None,
        "buys": [1, 2],
        "vendors": [("V-ROAST", "Harborline Roasters"), ("V-CERAM", "Ceramica Wholesale"),
                    ("V-PKG", "PackRight Supplies")],
        "customers": [("C-CAFE", "Corner Cafe Group"), ("C-HOTEL", "Grandview Hotels"),
                      ("C-WEB", "Webshop Walk-in")],
        "employees": [("E-3001", "Tomas", "Ruiz", "3200"), ("E-3002", "Ana", "Silva", "3000"),
                      ("E-3003", "Piet", "de Vries", "4300")],
        "department": ("D-STORE", "Store Operations"),
        "projects": [],
        "flows": {"mfg": False, "quality": False, "maintenance": False, "projects": False,
                  "crm": True, "stock": True},
    },
    {
        "slug": "professional-services",
        "template": "professional-services",
        "name": "Cedar & Vale Consulting",
        "coa": {
            "cash": _acct("1000", "Cash", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Accounts Receivable", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "paytax": _acct("2200", "Tax Payable", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "equity": _acct("3000", "Partner Equity", "EQUITY"),
            "rev": _acct("4000", "Consulting Fees", "REVENUE"),
            "salary": _acct("5000", "Consultant Salaries", "EXPENSE"),
            "opex": _acct("5100", "Subcontractor Costs", "EXPENSE"),
        },
        "pricediff": "opex",
        "categories": {"SVC": None},
        "items": [
            ("SVC-CONS", "Consulting Hour", "SERVICE", "SVC", "180.00", None),
            ("SVC-AUDIT", "Audit Day", "SERVICE", "SVC", "1400.00", None),
        ],
        "sell": 0,
        "make": None,
        "buys": [1],
        "vendors": [("V-SUBK", "Subcontract Partners LLC"), ("V-DATA", "InsightData Research"),
                    ("V-TRVL", "Corporate Travel Desk")],
        "customers": [("C-APEX", "Apex Capital"), ("C-HG", "Harbor & Gray LLP"),
                      ("C-LUMEN", "Lumen Health Group")],
        "employees": [("E-4001", "Ingrid", "Bauer", "7900"), ("E-4002", "Noah", "Clarke", "7300"),
                      ("E-4003", "Sofia", "Marino", "10000")],
        "department": ("D-CONSULT", "Consulting"),
        "projects": [("ENG-APEX", "Apex Capital — ERP Advisory", "180000"),
                     ("ENG-HG", "Harbor & Gray — Compliance Audit", "90000")],
        "flows": {"mfg": False, "quality": False, "maintenance": False, "projects": True,
                  "crm": True, "stock": False},
    },
    {
        "slug": "healthcare",
        "template": "healthcare",
        "name": "Riverbend Clinic",
        "coa": {
            "cash": _acct("1000", "Cash", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Patient Receivables", "ASSET"),
            "inv": _acct("1300", "Medical Supplies Inventory", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "grir": _acct("2100", "GR/IR Clearing", "LIABILITY"),
            "paytax": _acct("2200", "Tax Payable", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "equity": _acct("3000", "Practice Equity", "EQUITY"),
            "rev": _acct("4000", "Patient Service Revenue", "REVENUE"),
            "cogs": _acct("5000", "Medical Supplies Expense", "EXPENSE"),
            "salary": _acct("5100", "Clinical Staff Salaries", "EXPENSE"),
            "opex": _acct("6000", "Operating Expenses", "EXPENSE"),
        },
        "pricediff": "cogs",
        "categories": {"SUPPLY": "inv", "PHARMA": "inv"},
        "items": [
            ("MED-GLOVE", "Nitrile Gloves (Box)", "STOCKED", "SUPPLY", "28.00", "12.00"),
            ("MED-SYR", "Syringe 5ml (Box)", "STOCKED", "SUPPLY", "15.00", "6.00"),
            ("RX-AMOX", "Amoxicillin 500mg (Vial)", "STOCKED", "PHARMA", "32.00", "14.00"),
        ],
        "sell": 0,
        "make": None,
        "buys": [1, 2],
        "vendors": [("V-MEDS", "MedSupply Direct"), ("V-PHARM", "PharmaSource Inc"),
                    ("V-LINEN", "CleanLinen Services")],
        "customers": [("C-CASC", "Cascade Health Plan"), ("C-ALVA", "J. Alvarez"),
                      ("C-CHEN", "M. Chen")],
        "employees": [("E-5001", "Grace", "Okafor", "6800"), ("E-5002", "Liam", "Byrne", "5300"),
                      ("E-5003", "Yuki", "Tanaka", "9200")],
        "department": ("D-CLIN", "Clinical"),
        "projects": [],
        "flows": {"mfg": False, "quality": True, "maintenance": True, "projects": False,
                  "crm": False, "stock": True},
    },
    {
        "slug": "construction",
        "template": "construction",
        "name": "Stonebridge Construction",
        "coa": {
            "cash": _acct("1000", "Cash", "ASSET", "OPERATING", True),
            "ar": _acct("1100", "Accounts Receivable", "ASSET"),
            "inv": _acct("1300", "Materials Inventory", "ASSET"),
            "ap": _acct("2000", "Accounts Payable", "LIABILITY"),
            "grir": _acct("2100", "GR/IR Clearing", "LIABILITY"),
            "paytax": _acct("2250", "Tax Payable", "LIABILITY"),
            "wages": _acct("2300", "Wages Payable", "LIABILITY"),
            "equity": _acct("3000", "Owner Equity", "EQUITY"),
            "rev": _acct("4000", "Contract Revenue", "REVENUE"),
            "cogs": _acct("5000", "Job Costs - Materials", "EXPENSE"),
            "salary": _acct("5100", "Job Costs - Labour", "EXPENSE"),
            "opex": _acct("5300", "Equipment Operating Costs", "EXPENSE"),
        },
        "pricediff": "cogs",
        "categories": {"MAT": "inv"},
        "items": [
            ("PNL-WALL", "Prefab Wall Panel", "STOCKED", "MAT", "950.00", "580.00"),
            ("MAT-REBAR", "Rebar 12mm (Bundle)", "STOCKED", "MAT", None, "62.00"),
            ("MAT-CEM", "Cement (Pallet)", "STOCKED", "MAT", None, "210.00"),
        ],
        "sell": 0,
        "make": None,
        "buys": [1, 2],
        "vendors": [("V-STEEL", "IronPeak Steel"), ("V-CEM", "Foundry Cement Co"),
                    ("V-RENT", "HeavyRent Equipment")],
        "customers": [("C-CITY", "City of Ashford"), ("C-RIVDEV", "Riverside Developments"),
                      ("C-NHA", "Northgate Housing Assoc")],
        "employees": [("E-6001", "Owen", "Gallagher", "5200"), ("E-6002", "Priya", "Nair", "4800"),
                      ("E-6003", "Marek", "Novak", "7000")],
        "department": ("D-SITE", "Site Operations"),
        "projects": [("PRJ-TOWER", "Riverside Tower — Phase 1", "1200000"),
                     ("PRJ-DEPOT", "Hillcrest Depot Refit", "400000")],
        "flows": {"mfg": False, "quality": True, "maintenance": True, "projects": True,
                  "crm": True, "stock": True},
    },
]


_handlers_registered = False


async def bootstrap(p: dict) -> uuid.UUID:
    """Idempotently create the tenant, apply its industry template (if any), and provision the
    demo superuser + a Superuser role holding the entire permission catalog. DB-direct."""
    global _handlers_registered
    from sqlalchemy import select

    import app.core.bootstrap  # noqa: F401 — side effect: registers every module's permission keys
    from app.core.bootstrap import register_event_handlers
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
    from app.modules.industry.loader import apply_template

    if not _handlers_registered:
        register_event_handlers()  # template slices (COA/UoMs/…) apply via the event bus
        _handlers_registered = True

    slug, email = p["slug"], f"owner@{p['slug']}.test"
    async with build_session_factory(engine)() as db:
        with system_context():
            tenant = (
                await db.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one_or_none()
        if tenant is None:
            tenant = await provision_tenant(db, slug=slug, name=p["name"])
        if p.get("template"):
            await apply_template(db, tenant.id, p["template"])  # no-op when already applied

        with system_context():
            user = (
                await db.execute(
                    select(User).where(User.tenant_id == tenant.id, User.email == email)
                )
            ).scalar_one_or_none()
        if user is None:
            user = await provision_user(db, tenant.id, email=email, password=PASSWORD)

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
        tenant_id = tenant.id
    print(f"seed: bootstrap ok — tenant={slug} user={email} role=Superuser")
    return tenant_id


client = httpx.Client(base_url=BASE, timeout=60.0)


def login(slug: str) -> None:
    r = client.post(
        "/auth/login",
        json={"tenant_slug": slug, "email": f"owner@{slug}.test", "password": PASSWORD},
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
_GROUP_NAMES = {
    "1": "Assets", "2": "Liabilities", "3": "Equity", "4": "Revenue", "5": "Expenses",
    "6": "Operating Expenses",  # seed-created 6xxx accounts on template tenants
}


def seed_finance(p: dict) -> dict:
    ctx = {}
    get_or_create(
        "/finance/currencies", "code", {"code": "USD", "name": "US Dollar", "is_functional": True}
    )
    if not p["template"]:  # templates ship their own currency + tax codes
        get_or_create("/finance/currencies", "code", {"code": "EUR", "name": "Euro"})
        get_or_create(
            "/finance/tax-codes",
            "code",
            {"code": "STD", "name": "Standard VAT 10%", "rate_percent": "10", "jurisdiction": "US"},
        )
        get_or_create(
            "/finance/tax-codes",
            "code",
            {"code": "ZERO", "name": "Zero Rated", "rate_percent": "0"},
        )
    ctx["currency"] = "USD"

    # account groups: template tenants ship groups 1-5; acme keeps its single 1000 group
    groups = {}

    def group_for(code: str) -> str:
        gcode = code[0] if p["template"] else "1000"
        if gcode not in groups:
            groups[gcode] = get_or_create(
                "/finance/account-groups",
                "code",
                {"code": gcode, "name": _GROUP_NAMES.get(gcode, "Assets")},
            )
        return groups[gcode]["id"]

    accts = {}
    for role, spec in p["coa"].items():
        body = {
            "code": spec["code"],
            "name": spec["name"],
            "account_type": spec["type"],
            "account_group_id": group_for(spec["code"]),
            "is_cash_equivalent": spec["cash"],
        }
        if spec["cf"]:
            body["cash_flow_category"] = spec["cf"]
        accts[role] = get_or_create("/finance/accounts", "code", body)
    ctx["accounts"] = {role: a["id"] for role, a in accts.items()}
    acct_id = ctx["accounts"]

    # posting defaults so every downstream flow (billing, GR, AP bill, payroll, production)
    # resolves its GL accounts
    defaults = {
        "ar_control": "ar",
        "sales_revenue": "rev",
        "ap_control": "ap",
        "salary_expense": "salary",
        "wages_payable": "wages",
        "payroll_tax_payable": "paytax",
    }
    if p["flows"]["stock"]:
        defaults["gr_ir_clearing"] = "grir"
        defaults["purchase_price_variance"] = p["pricediff"]
    if p["flows"]["mfg"]:
        defaults["wip_clearing"] = "wip"
        defaults["production_variance"] = "prodvar"
    for purpose, role in defaults.items():
        put("/finance/posting-defaults", {"purpose": purpose, "account_id": acct_id[role]})

    fy = get_or_create(
        "/finance/fiscal-years",
        "code",
        {"code": "FY2026", "name": "Fiscal Year 2026", "start_date": "2026-01-01"},
    )
    # open every period the window touches (March, for the opening stock, through July)
    for per in items(f"/finance/fiscal-periods?fiscal_year_id={fy['id']}"):
        overlaps = per["start_date"] <= TODAY.isoformat() and per["end_date"] >= OPENING.isoformat()
        if overlaps and per["status"] != "OPEN":
            post(f"/finance/fiscal-periods/{per['id']}/open")

    cc = get_or_create("/finance/cost-centers", "code", {"code": "CC-OPS", "name": "Operations"})
    get_or_create(
        "/finance/cost-centers", "code", {"code": "CC-SALES", "name": "Sales & Marketing"}
    )
    pc = get_or_create(
        "/finance/profit-centers", "code", {"code": "PC-MAIN", "name": "Main Business"}
    )
    ctx["cost_center"] = cc["id"]
    ctx["profit_center"] = pc["id"]

    # opening capital + monthly overhead journals — only on a fresh tenant
    if empty("/finance/journal-entries"):
        je = post(
            "/finance/journal-entries",
            {
                "posting_date": START.isoformat(),
                "currency_code": "USD",
                "description": "Opening capital injection",
                "document_type": "JOURNAL",
                "lines": [
                    {
                        "account_id": acct_id["cash"],
                        "description": "Cash in",
                        "transaction_debit_amount": "250000",
                        "transaction_credit_amount": "0",
                        "cost_center_id": cc["id"],
                        "profit_center_id": pc["id"],
                    },
                    {
                        "account_id": acct_id["equity"],
                        "description": "Opening equity",
                        "transaction_debit_amount": "0",
                        "transaction_credit_amount": "250000",
                    },
                ],
            },
        )
        if je:
            post(f"/finance/journal-entries/{je['id']}/post")
        for m_start, _m_end in MONTHS:
            je = post(
                "/finance/journal-entries",
                {
                    "posting_date": m_start.isoformat(),
                    "currency_code": "USD",
                    "description": f"Rent & utilities {m_start:%B %Y}",
                    "document_type": "JOURNAL",
                    "lines": [
                        {
                            "account_id": acct_id["opex"],
                            "description": "Rent & utilities",
                            "transaction_debit_amount": "4200",
                            "transaction_credit_amount": "0",
                            "cost_center_id": cc["id"],
                        },
                        {
                            "account_id": acct_id["cash"],
                            "description": "Rent & utilities",
                            "transaction_debit_amount": "0",
                            "transaction_credit_amount": "4200",
                        },
                    ],
                },
            )
            if je:
                post(f"/finance/journal-entries/{je['id']}/post")
    return ctx


# ── Inventory ────────────────────────────────────────────────────────────────
def seed_inventory(p: dict, fin: dict) -> dict:
    ctx = {}
    ea = get_or_create("/inventory/uoms", "code", {"code": "EA", "name": "Each"})
    get_or_create("/inventory/uoms", "code", {"code": "HR", "name": "Hour"})
    ctx["uom"] = ea["id"]

    cats = {}
    for cat_code, inv_role in p["categories"].items():
        cat = get_or_create(
            "/inventory/item-categories", "code", {"code": cat_code, "name": cat_code}
        )
        cats[cat_code] = cat
        if inv_role:  # wire the three valuation accounts (required before valued stock moves)
            patch(
                f"/inventory/item-categories/{cat['id']}",
                {
                    "inventory_account_id": fin["accounts"][inv_role],
                    "cogs_account_id": fin["accounts"]["cogs"],
                    "price_difference_account_id": fin["accounts"][p["pricediff"]],
                },
            )

    if p["flows"]["stock"]:
        wh = get_or_create(
            "/inventory/warehouses", "code", {"code": "WH1", "name": "Main Warehouse"}
        )
        ctx["warehouse"] = wh["id"]
        bin_ = get_or_create(
            "/inventory/bins",
            "code",
            {"warehouse_id": wh["id"], "code": "A-01", "name": "Aisle A Bin 01",
             "is_default": True},
        )
        ctx["bin"] = bin_["id"]

    it_ids = {}
    for code, name, itype, cat_code, _price, _cost in p["items"]:
        body = {
            "item_code": code,
            "name": name,
            "item_type": itype,
            "category_id": cats[cat_code]["id"],
            "base_uom_id": ea["id"],
        }
        it_ids[code] = get_or_create("/inventory/items", "item_code", body)["id"]
    ctx["items"] = it_ids

    # opening stock for everything stocked, dated at the start of the window
    if p["flows"]["stock"] and empty("/inventory/stock-moves"):
        for code, _name, itype, _cat, price, cost in p["items"]:
            if itype != "STOCKED":
                continue
            qty = "800" if price else "600"  # sellables cover 3 months of orders
            post(
                "/inventory/stock-moves",
                {
                    "move_type": "ADJUSTMENT",
                    "item_id": it_ids[code],
                    "quantity": qty,
                    "to_bin_id": ctx["bin"],
                    "move_date": OPENING.isoformat(),
                    "unit_cost": cost or "1.00",
                    "reference": "Opening stock",
                },
            )
    return ctx


# ── Procurement (procure-to-pay) ─────────────────────────────────────────────
def _run_po_cycle(p, fin, inv, vendor_id, item_idx, qty, order_date, match_invoice):
    """One PO → approve → send → goods-receipt → post [→ invoice-match → post] cycle."""
    code, _n, _t, _c, _p, cost = p["items"][item_idx]
    po = post(
        "/procurement/purchase-orders",
        {
            "vendor_id": vendor_id,
            "currency_code": "USD",
            "order_date": order_date.isoformat(),
            "expected_date": (order_date + timedelta(days=3)).isoformat(),
            "lines": [
                {
                    "item_id": inv["items"][code],
                    "quantity": str(qty),
                    "uom_id": inv["uom"],
                    "unit_cost": cost,
                }
            ],
        },
    )
    if not po:
        return
    post(f"/procurement/purchase-orders/{po['id']}/decision", {"decision": "APPROVED"})
    post(f"/procurement/purchase-orders/{po['id']}/send")
    po_lines = get(f"/procurement/purchase-orders/{po['id']}").get("lines", [])
    if not po_lines:
        return
    gr = post(
        "/procurement/goods-receipts",
        {
            "purchase_order_id": po["id"],
            "warehouse_id": inv["warehouse"],
            "receipt_date": (order_date + timedelta(days=3)).isoformat(),
            "lines": [
                {
                    "purchase_order_line_id": po_lines[0]["id"],
                    "bin_id": inv["bin"],
                    "received_quantity": str(qty),
                    "requires_inspection": False,
                }
            ],
        },
    )
    if gr:
        post(f"/procurement/goods-receipts/{gr['id']}/post")
    if match_invoice and gr:
        match = post(
            "/procurement/invoice-matches",
            {
                "purchase_order_id": po["id"],
                "vendor_invoice_ref": f"INV-{order_date:%y%m%d}",
                "invoice_date": (order_date + timedelta(days=5)).isoformat(),
                "lines": [
                    {
                        "purchase_order_line_id": po_lines[0]["id"],
                        "matched_quantity": str(qty),
                        "unit_price": cost,
                    }
                ],
            },
        )
        if match:
            post(f"/procurement/invoice-matches/{match['id']}/post")


def seed_procurement(p: dict, fin: dict, inv: dict) -> dict:
    ctx = {}
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
        for c, n in p["vendors"]
    }
    ctx["vendors"] = vids
    vendor0 = vids[p["vendors"][0][0]]

    if not p["flows"]["stock"]:
        return ctx  # service business: AP runs as direct vendor bills (seed_direct_invoices)

    for idx in p["buys"]:
        post(
            f"/procurement/vendors/{vendor0}/approved-items",
            {"item_id": inv["items"][p["items"][idx][0]]},
        )

    if not empty("/procurement/purchase-orders"):
        return ctx

    # first cycle goes the long way: requisition → submit → convert-to-po (falls back to a
    # direct PO when an approval preset holds the requisition)
    first_item = p["items"][p["buys"][0]]
    req = post(
        "/procurement/requisitions",
        {
            "needed_by_date": WEEKS[0].isoformat(),
            "notes": "Restock",
            "lines": [
                {
                    "item_id": inv["items"][first_item[0]],
                    "description": first_item[1],
                    "quantity": "200",
                    "uom_id": inv["uom"],
                    "estimated_unit_cost": first_item[5],
                    "currency_code": "USD",
                }
            ],
        },
    )
    po = None
    if req:
        post(f"/procurement/requisitions/{req['id']}/submit")
        po = post(
            f"/procurement/requisitions/{req['id']}/convert-to-po",
            {
                "vendor_id": vendor0,
                "order_date": WEEKS[0].isoformat(),
                "expected_date": WEEKS[0].isoformat(),
            },
        )
    if po:
        post(f"/procurement/purchase-orders/{po['id']}/decision", {"decision": "APPROVED"})
        post(f"/procurement/purchase-orders/{po['id']}/send")
        lines = get(f"/procurement/purchase-orders/{po['id']}").get("lines", [])
        if lines:
            gr = post(
                "/procurement/goods-receipts",
                {
                    "purchase_order_id": po["id"],
                    "warehouse_id": inv["warehouse"],
                    "receipt_date": WEEKS[0].isoformat(),
                    "lines": [
                        {
                            "purchase_order_line_id": lines[0]["id"],
                            "bin_id": inv["bin"],
                            "received_quantity": "200",
                            "requires_inspection": False,
                        }
                    ],
                },
            )
            if gr:
                post(f"/procurement/goods-receipts/{gr['id']}/post")
    else:
        _run_po_cycle(p, fin, inv, vendor0, p["buys"][0], 200, WEEKS[0], match_invoice=True)

    # then a biweekly P2P cycle across the window, alternating items; invoice-match every
    # other cycle so some receipts stay open on the GR/IR account
    for i, week in enumerate(WEEKS[2::2]):
        item_idx = p["buys"][i % len(p["buys"])]
        _run_po_cycle(
            p, fin, inv, vendor0, item_idx, 150 + 30 * i, week, match_invoice=(i % 2 == 0)
        )
    return ctx


# ── Quality ──────────────────────────────────────────────────────────────────
def seed_quality(p: dict, inv: dict, proc: dict) -> None:
    """Generate an inspection lot via an inspection-required goods receipt, then decide it."""
    vid = proc["vendors"][p["vendors"][1][0]]
    insp_item = p["items"][p["buys"][-1]]
    post(f"/procurement/vendors/{vid}/approved-items", {"item_id": inv["items"][insp_item[0]]})
    if not empty("/quality/inspection-lots"):
        return
    po = post(
        "/procurement/purchase-orders",
        {
            "vendor_id": vid,
            "currency_code": "USD",
            "order_date": WEEKS[1].isoformat(),
            "lines": [
                {
                    "item_id": inv["items"][insp_item[0]],
                    "quantity": "100",
                    "uom_id": inv["uom"],
                    "unit_cost": insp_item[5],
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
            "receipt_date": WEEKS[1].isoformat(),
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


# ── Sales (order-to-cash) ────────────────────────────────────────────────────
def seed_sales(p: dict, fin: dict, inv: dict) -> dict:
    ctx = {}
    grp = get_or_create(
        "/sales/customer-groups", "code", {"code": "STD", "name": "Standard Customers"}
    )
    cids = {
        c: get_or_create(
            "/sales/customers",
            "customer_code",
            {
                "customer_code": c,
                "name": n,
                "default_currency_code": "USD",
                "customer_group_id": grp["id"],
                "credit_limit": "500000",
                "email": f"buyer@{c.lower()}.test",
            },
        )["id"]
        for c, n in p["customers"]
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
        for code, _n, _t, _c, price, _cost in p["items"]:
            if price:
                post(
                    f"/sales/price-lists/{pl['id']}/items",
                    {"item_id": inv["items"][code], "unit_price": price},
                )

    if not empty("/sales/orders"):
        return ctx

    sell = p["items"][p["sell"]]
    customer_codes = [c for c, _ in p["customers"]]

    # first cycle goes the long way: quote → send → accept → convert-to-order
    q = post(
        "/sales/quotes",
        {
            "customer_id": cids[customer_codes[0]],
            "currency_code": "USD",
            "quote_date": WEEKS[0].isoformat(),
            "valid_until": "2026-08-31",
            "notes": "Opening order",
            "lines": [
                {
                    "item_id": inv["items"][sell[0]],
                    "quantity": "25",
                    "uom_id": inv["uom"],
                    "unit_price": sell[4],
                }
            ],
        },
    )
    orders = []
    if q:
        post(f"/sales/quotes/{q['id']}/send")
        post(f"/sales/quotes/{q['id']}/accept")
        o = post(
            f"/sales/quotes/{q['id']}/convert-to-order",
            {"order_date": WEEKS[0].isoformat(), "requested_date": WEEKS[0].isoformat()},
        )
        if o:
            orders.append((o, WEEKS[0], 25))

    # weekly direct orders, rotating customers and varying quantities
    for i, week in enumerate(WEEKS[1:], start=1):
        qty = 15 + (i * 7) % 26
        o = post(
            "/sales/orders",
            {
                "customer_id": cids[customer_codes[i % len(customer_codes)]],
                "currency_code": "USD",
                "order_date": week.isoformat(),
                "requested_date": (week + timedelta(days=7)).isoformat(),
                "lines": [
                    {
                        "item_id": inv["items"][sell[0]],
                        "quantity": str(qty),
                        "uom_id": inv["uom"],
                        "unit_price": sell[4],
                    }
                ],
            },
        )
        if o:
            orders.append((o, week, qty))

    for idx, (order, week, qty) in enumerate(orders):
        post(f"/sales/orders/{order['id']}/confirm")
        if not p["flows"]["stock"]:
            continue  # service business: fee invoices land via seed_direct_invoices
        if idx == len(orders) - 1:
            continue  # leave the newest order open (undelivered) for dashboards
        olines = get(f"/sales/orders/{order['id']}").get("lines", [])
        if not olines:
            continue
        deliver_qty = qty // 2 if idx == len(orders) - 2 else qty  # one partial delivery
        dl = post(
            "/sales/deliveries",
            {
                "sales_order_id": order["id"],
                "warehouse_id": inv["warehouse"],
                "delivery_date": (week + timedelta(days=2)).isoformat(),
                "lines": [
                    {
                        "sales_order_line_id": olines[0]["id"],
                        "bin_id": inv["bin"],
                        "quantity": str(deliver_qty),
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
                "billing_date": (week + timedelta(days=3)).isoformat(),
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


# ── Direct AR/AP invoices (service businesses without stock flows) ───────────
def seed_direct_invoices(p: dict, fin: dict, sales: dict, prj: dict) -> None:
    """Professional-services order-to-cash/procure-to-pay: monthly posted fee invoices per
    client (project-dimensioned) and monthly posted subcontractor vendor bills."""
    acct = fin["accounts"]
    project_ids = list(prj.get("projects", {}).values())
    if empty("/finance/customer-invoices"):
        for m_i, (_m_start, m_end) in enumerate(MONTHS):
            for c_i, (code, name) in enumerate(p["customers"][:2]):
                inv_doc = post(
                    "/finance/customer-invoices",
                    {
                        "partner_id": sales["customers"][code],
                        "partner_name": name,
                        "invoice_date": m_end.isoformat(),
                        "due_date": (m_end + timedelta(days=30)).isoformat(),
                        "currency_code": "USD",
                        "ar_account_id": acct["ar"],
                        "description": f"Professional fees {m_end:%B %Y}",
                        "lines": [
                            {
                                "account_id": acct["rev"],
                                "description": "Consulting fees",
                                "net_amount": str(12000 + 2500 * m_i + 1500 * c_i),
                                "cost_center_id": fin["cost_center"],
                                "project_id": project_ids[c_i % len(project_ids)]
                                if project_ids
                                else None,
                            }
                        ],
                    },
                )
                if inv_doc:
                    post(f"/finance/customer-invoices/{inv_doc['id']}/post")
    if empty("/finance/vendor-bills"):
        vendors = items("/procurement/vendors")
        if vendors:
            v = vendors[0]
            for m_i, (_m_start, m_end) in enumerate(MONTHS):
                bill = post(
                    "/finance/vendor-bills",
                    {
                        "partner_id": v["id"],
                        "partner_name": v["name"],
                        "bill_date": m_end.isoformat(),
                        "due_date": (m_end + timedelta(days=30)).isoformat(),
                        "currency_code": "USD",
                        "ap_account_id": acct["ap"],
                        "bill_external_ref": f"SUB-{m_end:%y%m}",
                        "lines": [
                            {
                                "account_id": acct["opex"],
                                "description": "Subcontracted delivery work",
                                "net_amount": str(4500 + 800 * m_i),
                                "cost_center_id": fin["cost_center"],
                            }
                        ],
                    },
                )
                if bill:
                    post(f"/finance/vendor-bills/{bill['id']}/post")


# ── Manufacturing (make-to-stock) ────────────────────────────────────────────
def seed_manufacturing(p: dict, fin: dict, inv: dict) -> None:
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

    make = p["items"][p["make"]]
    comps = [p["items"][i] for i in p["buys"]]
    if empty("/manufacturing/boms"):
        bom = post(
            "/manufacturing/boms",
            {
                "item_id": inv["items"][make[0]],
                "version": "v1",
                "name": f"{make[1]} BOM",
                "base_quantity": "1",
                "uom_id": inv["uom"],
            },
        )
        if bom:
            for comp, qty_per in zip(comps, ("4", "1"), strict=False):
                post(
                    f"/manufacturing/boms/{bom['id']}/components",
                    {
                        "component_item_id": inv["items"][comp[0]],
                        "quantity_per": qty_per,
                        "uom_id": inv["uom"],
                    },
                )
            post(f"/manufacturing/boms/{bom['id']}/activate")

    if empty("/manufacturing/routings"):
        rt = post(
            "/manufacturing/routings",
            {"item_id": inv["items"][make[0]], "version": "v1", "name": f"{make[1]} Routing"},
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

    # one production order per month: release → issue components → finish to stock
    if empty("/manufacturing/production-orders"):
        for m_i, (m_start, _m_end) in enumerate(MONTHS):
            qty = 20 + 10 * m_i
            work_date = m_start + timedelta(days=9)
            po = post(
                "/manufacturing/production-orders",
                {
                    "item_id": inv["items"][make[0]],
                    "quantity": str(qty),
                    "warehouse_id": inv["warehouse"],
                    "planned_start_date": work_date.isoformat(),
                },
            )
            if not po:
                continue
            post(f"/manufacturing/production-orders/{po['id']}/release")
            post(
                f"/manufacturing/production-orders/{po['id']}/issue-components",
                {"move_date": work_date.isoformat()},
            )
            post(
                f"/manufacturing/production-orders/{po['id']}/finish",
                {
                    "finished_quantity": str(qty),
                    "finished_bin_id": inv["bin"],
                    "move_date": (work_date + timedelta(days=2)).isoformat(),
                },
            )


# ── Maintenance ──────────────────────────────────────────────────────────────
def seed_maintenance(p: dict, fin: dict) -> None:
    eq = get_or_create(
        "/maintenance/equipment",
        "code",
        {
            "code": "EQ-MAIN1",
            "name": "Primary Plant Equipment",
            "location": "Main Site",
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
                "code": "MP-MONTHLY",
                "name": "Monthly Service",
                "equipment_id": eq["id"],
                "interval_value": 1,
                "interval_unit": "MONTHS",
                "task_description": "Lubricate & inspect",
                "start_date": START.isoformat(),
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
                "description": "Replace worn bearing",
                "scheduled_date": WEEKS[6].isoformat(),
                "estimated_cost": "800",
            },
        )


# ── HR (time & payroll) ──────────────────────────────────────────────────────
def seed_hr(p: dict, fin: dict, prj: dict) -> dict:
    ctx = {}
    d_code, d_name = p["department"]
    dept = get_or_create(
        "/hr/departments",
        "code",
        {"code": d_code, "name": d_name, "cost_center_id": fin["cost_center"]},
    )
    get_or_create("/hr/departments", "code", {"code": "D-ADMIN", "name": "Administration"})
    pos = get_or_create(
        "/hr/positions",
        "code",
        {"code": "P-STAFF", "title": "Staff", "department_id": dept["id"]},
    )
    get_or_create(
        "/hr/positions", "code", {"code": "P-MGR", "title": "Manager", "department_id": dept["id"]}
    )

    eids = {}
    for code, fn, ln, salary in p["employees"]:
        eids[code] = get_or_create(
            "/hr/employees",
            "employee_code",
            {
                "employee_code": code,
                "first_name": fn,
                "last_name": ln,
                "email": f"{fn.lower()}@{p['slug']}.test",
                "department_id": dept["id"],
                "position_id": pos["id"],
                "hire_date": "2025-06-01",
                "base_salary": salary,
                "currency_code": "USD",
            },
        )["id"]
    ctx["employees"] = eids
    emp_codes = list(eids)

    lt = get_or_create(
        "/hr/leave-types",
        "code",
        {"code": "LT-ANNUAL", "name": "Annual Leave", "accrual_amount": "1.75"},
    )
    if empty("/hr/leave-requests"):
        for e_i, (start, days) in enumerate([(WEEKS[5], 5), (WEEKS[9], 2)]):
            lr = post(
                "/hr/leave-requests",
                {
                    "employee_id": eids[emp_codes[e_i]],
                    "leave_type_id": lt["id"],
                    "start_date": start.isoformat(),
                    "end_date": (start + timedelta(days=days - 1)).isoformat(),
                    "days": str(days),
                    "reason": "Annual leave",
                },
            )
            if lr:
                post(f"/hr/leave-requests/{lr['id']}/submit")

    # weekly timesheets across the window: employee 1 every week, employee 2 biweekly,
    # entries allocated to a project (when the tenant runs projects) and the cost centre
    project_ids = list(prj.get("projects", {}).values())
    if empty("/hr/timesheets"):
        for w_i, week in enumerate(WEEKS):
            for e_i in (0, 1) if w_i % 2 == 0 else (0,):
                ts = post(
                    "/hr/timesheets",
                    {
                        "employee_id": eids[emp_codes[e_i]],
                        "period_start": week.isoformat(),
                        "period_end": (week + timedelta(days=6)).isoformat(),
                        "notes": f"Week of {week.isoformat()}",
                    },
                )
                if not ts:
                    continue
                for day in range(5):
                    body = {
                        "entry_date": (week + timedelta(days=day)).isoformat(),
                        "hours": "8",
                        "cost_center_id": fin["cost_center"],
                        "task_description": "Client / production work",
                        "is_billable": True,
                    }
                    if project_ids:
                        body["project_id"] = project_ids[w_i % len(project_ids)]
                    post(f"/hr/timesheets/{ts['id']}/time-entries", body)
                post(f"/hr/timesheets/{ts['id']}/submit")

    # monthly payroll runs, posted — lands salary expense + payables on the GL
    if empty("/hr/payroll-runs"):
        for m_start, m_end in MONTHS:
            run = post(
                "/hr/payroll-runs",
                {
                    "period_start": m_start.isoformat(),
                    "period_end": m_end.isoformat(),
                    "pay_date": m_end.isoformat(),
                },
            )
            if run:
                post(f"/hr/payroll-runs/{run['id']}/post")
    return ctx


# ── Projects ─────────────────────────────────────────────────────────────────
def seed_projects(p: dict, fin: dict, sales: dict) -> dict:
    ctx = {"projects": {}}
    customer_ids = list(sales.get("customers", {}).values())
    for i, (code, name, budget) in enumerate(p["projects"]):
        proj = get_or_create(
            "/projects",
            "code",
            {
                "code": code,
                "name": name,
                "status": "ACTIVE",
                "customer_id": customer_ids[i % len(customer_ids)] if customer_ids else None,
                "cost_center_id": fin["cost_center"],
                "start_date": START.isoformat(),
                "budget_amount": budget,
            },
        )
        ctx["projects"][code] = proj["id"]
        if empty(f"/projects/{proj['id']}/wbs-elements"):
            post(
                f"/projects/{proj['id']}/wbs-elements",
                {"code": f"{code}-1", "name": "Planning", "budget_amount": "40000"},
            )
            post(
                f"/projects/{proj['id']}/wbs-elements",
                {
                    "code": f"{code}-2",
                    "name": "Execution",
                    "is_billable": True,
                    "budget_amount": budget,
                },
            )
    return ctx


# ── CRM ──────────────────────────────────────────────────────────────────────
def seed_crm(p: dict, hr: dict) -> None:
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
                    "due_date": TODAY.isoformat(),
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
_VERIFY_CORE = {
    "finance/accounts": "Accounts",
    "finance/journal-entries": "Journal entries",
    "inventory/items": "Items",
    "procurement/vendors": "Vendors",
    "procurement/purchase-orders": "Purchase orders",
    "sales/customers": "Customers",
    "sales/orders": "Sales orders",
    "hr/employees": "Employees",
    "hr/timesheets": "Timesheets",
    "hr/payroll-runs": "Payroll runs",
}
_VERIFY_FLOW = {
    "stock": {
        "inventory/stock-moves": "Stock moves",
        "procurement/goods-receipts": "Goods receipts",
        "sales/deliveries": "Deliveries",
        "sales/billings": "Billings",
    },
    "mfg": {"manufacturing/production-orders": "Production orders"},
    "quality": {"quality/inspection-lots": "Inspection lots"},
    "maintenance": {"maintenance/maintenance-orders": "Maintenance orders"},
    "projects": {"projects": "Projects"},
    "crm": {"crm/leads": "Leads", "crm/opportunities": "Opportunities"},
}


def summarize(p: dict) -> None:
    checks = dict(_VERIFY_CORE)
    for flow, paths in _VERIFY_FLOW.items():
        if p["flows"].get(flow):
            checks.update(paths)
    print(f"\n=== {p['slug']} — seed summary (row counts per list endpoint) ===")
    for path, label in checks.items():
        try:
            n = len(items("/" + path))
        except Exception as e:  # noqa: BLE001
            n = f"ERR {e}"
        print(f"  {label:<20} {n}")


def seed_tenant(p: dict) -> None:
    asyncio.run(bootstrap(p))
    login(p["slug"])
    fin = seed_finance(p)
    inv = seed_inventory(p, fin)
    proc = seed_procurement(p, fin, inv)
    if p["flows"]["quality"] and p["flows"]["stock"]:
        seed_quality(p, inv, proc)
    sales = seed_sales(p, fin, inv)
    prj = seed_projects(p, fin, sales) if p["flows"]["projects"] else {}
    if not p["flows"]["stock"]:
        seed_direct_invoices(p, fin, sales, prj)
    if p["flows"]["mfg"]:
        seed_manufacturing(p, fin, inv)
    if p["flows"]["maintenance"]:
        seed_maintenance(p, fin)
    hr = seed_hr(p, fin, prj)
    if p["flows"]["crm"]:
        seed_crm(p, hr)
    summarize(p)


def main() -> None:
    if not _seed_enabled():
        return
    for p in PROFILES:
        seed_tenant(p)


# ── 16.2: --volume high-volume tenant (PERFORMANCE §5) ───────────────────────
VOLUME_PROFILE = {"slug": "volume", "template": None, "name": "Volume Perf"}
V_ITEMS, V_ORDERS, V_MOVES, V_ENTRIES = 5_000, 10_000, 50_000, 25_200  # 25 200×4 = 100 800 lines
_CHUNK = 5_000


async def seed_volume() -> None:
    """Direct bulk-insert seed (no HTTP): ≥100k journal lines, ≥50k stock moves, ≥10k orders,
    ≥5k items, 3 fiscal years with every period OPEN. Bypasses the service layer on purpose —
    PERFORMANCE §5 requires set-based inserts that finish in minutes — but keeps the DB
    invariants honest: balanced posted journals in open periods (the period trigger checks
    each header), one-sided lines, positive quants, and a core_documents row per document."""
    import calendar
    import random
    from decimal import Decimal

    from sqlalchemy import func, insert, select

    from app.core.db import engine
    from app.core.docflow import Document
    from app.modules.finance.constants import JOURNAL_ENTRY_DOC_TYPE
    from app.modules.finance.models.accounts import Account, AccountGroup, FiscalPeriod, FiscalYear
    from app.modules.finance.models.fx import Currency
    from app.modules.finance.models.journal import JournalEntry, JournalLine
    from app.modules.inventory.constants import STOCK_MOVE_DOC_TYPE
    from app.modules.inventory.models.costing import ItemValuation
    from app.modules.inventory.models.masters import Item, ItemCategory, Uom
    from app.modules.inventory.models.stock import Bin, StockMove, StockQuant, Warehouse
    from app.modules.sales.constants.documents import SALES_ORDER_DOC_TYPE
    from app.modules.sales.models.customers import Customer, CustomerGroup
    from app.modules.sales.models.orders import SalesOrder, SalesOrderLine

    t0 = time.perf_counter()
    tenant_id = await bootstrap(VOLUME_PROFILE)
    now = datetime.now(UTC)
    rng = random.Random(42)

    def row(**extra) -> dict:
        return {"id": uuid.uuid4(), "tenant_id": tenant_id,
                "created_at": now, "updated_at": now, **extra}

    async def bulk(conn, table, rows: list[dict]) -> None:
        for i in range(0, len(rows), _CHUNK):
            await conn.execute(insert(table), rows[i : i + _CHUNK])

    async with engine.begin() as conn:
        already = await conn.scalar(
            select(func.count()).select_from(JournalEntry.__table__).where(
                JournalEntry.__table__.c.tenant_id == tenant_id
            )
        )
        if already:
            print(f"seed --volume: tenant already has {already} journal entries — skipping.")
            return

        # ── masters ──────────────────────────────────────────────────────
        await conn.execute(
            insert(Currency.__table__),
            [row(code="USD", name="US Dollar", decimal_places=2, is_functional=True)],
        )
        grp = row(code="1", name="Volume COA", parent_id=None, sort_order=1)
        await conn.execute(insert(AccountGroup.__table__), [grp])
        acct_specs = [
            ("1000", "Cash", "ASSET"), ("1100", "Accounts Receivable", "ASSET"),
            ("1200", "Inventory", "ASSET"), ("2000", "Accounts Payable", "LIABILITY"),
            ("3000", "Equity", "EQUITY"), ("4000", "Revenue", "REVENUE"),
            ("5000", "COGS", "EXPENSE"),
        ]
        accounts = {}
        acct_rows = []
        for code, name, atype in acct_specs:
            r = row(
                code=code, name=name, account_type=atype,
                normal_balance="DEBIT" if atype in ("ASSET", "EXPENSE") else "CREDIT",
                is_postable=True, cash_flow_category=None,
                is_cash_equivalent=(code == "1000"), account_group_id=grp["id"],
                is_active=True, is_monetary=True,
            )
            accounts[code] = r["id"]
            acct_rows.append(r)
        await conn.execute(insert(Account.__table__), acct_rows)

        # 3 fiscal years (2024-2026), 12 monthly periods each, ALL OPEN
        periods = []  # (start, end, id)
        fy_rows, per_rows = [], []
        for year in (2024, 2025, 2026):
            fy = row(
                code=f"FY{year}", name=f"Fiscal Year {year}", start_date=date(year, 1, 1),
                end_date=date(year, 12, 31), status="OPEN",
            )
            fy_rows.append(fy)
            for m in range(1, 13):
                p_start = date(year, m, 1)
                p_end = date(year, m, calendar.monthrange(year, m)[1])
                pr = row(
                    fiscal_year_id=fy["id"], period_number=m, name=f"{year}-{m:02d}",
                    start_date=p_start, end_date=p_end, status="OPEN",
                )
                per_rows.append(pr)
                periods.append((p_start, p_end, pr["id"]))
        await conn.execute(insert(FiscalYear.__table__), fy_rows)
        await conn.execute(insert(FiscalPeriod.__table__), per_rows)

        def period_for(d: date) -> uuid.UUID:
            return periods[(d.year - 2024) * 12 + d.month - 1][2]

        uom = row(code="EA", name="Each")
        await conn.execute(insert(Uom.__table__), [uom])
        cat = row(
            code="GEN", name="General", default_costing_method="MOVING_AVERAGE",
            inventory_account_id=accounts["1200"], cogs_account_id=accounts["5000"],
            price_difference_account_id=accounts["5000"],
        )
        await conn.execute(insert(ItemCategory.__table__), [cat])
        wh = row(code="WH1", name="Volume Warehouse", is_active=True)
        await conn.execute(insert(Warehouse.__table__), [wh])
        bin_ = row(code="A-01", name="Bin A-01", warehouse_id=wh["id"],
                   is_default=True, is_active=True)
        await conn.execute(insert(Bin.__table__), [bin_])

        cgrp = row(code="STD", name="Standard")
        await conn.execute(insert(CustomerGroup.__table__), [cgrp])
        cust_rows = [
            row(
                customer_code=f"VC-{i:03d}", name=f"Volume Customer {i}", status="ACTIVE",
                customer_group_id=cgrp["id"], default_currency_code="USD",
                payment_terms_days=30, credit_limit=Decimal("1000000"),
                tax_reference=None, email=None, phone=None, address=None,
            )
            for i in range(1, 51)
        ]
        await conn.execute(insert(Customer.__table__), cust_rows)
        customer_ids = [c["id"] for c in cust_rows]

        # ── ≥5k items ────────────────────────────────────────────────────
        item_rows = []
        item_costs = []
        for i in range(V_ITEMS):
            cost = Decimal(5 + i % 95)
            item_costs.append(cost)
            item_rows.append(
                row(
                    item_code=f"VITM-{i:05d}", name=f"Volume Item {i}", description=None,
                    item_type="STOCKED", category_id=cat["id"], base_uom_id=uom["id"],
                    costing_method="MOVING_AVERAGE", tracking_mode="NONE", is_active=True,
                    reorder_point=None, reorder_quantity=None,
                )
            )
        await bulk(conn, Item.__table__, item_rows)
        item_ids = [r["id"] for r in item_rows]
        span_start, span_days = date(2024, 1, 1), 911  # through 2026-06-30

        # ── ≥50k stock moves (+ quants + valuations) ─────────────────────
        doc_rows, move_rows = [], []
        on_hand = [0] * V_ITEMS
        for i in range(V_MOVES):
            if i < V_ITEMS:  # opening receipt per item
                item_i, mtype, qty, d = i, "RECEIPT", 1000, span_start
            else:
                item_i = rng.randrange(V_ITEMS)
                d = span_start + timedelta(days=rng.randrange(span_days))
                if on_hand[item_i] >= 10 and rng.random() < 0.45:
                    mtype, qty = "ISSUE", 10
                else:
                    mtype, qty = "RECEIPT", 25
            on_hand[item_i] += qty if mtype == "RECEIPT" else -qty
            doc = row(doc_type=STOCK_MOVE_DOC_TYPE, doc_id=None,
                      doc_number=f"STK-VOL-{i:06d}", status="POSTED")
            move = row(
                document_id=doc["id"], move_number=f"STK-VOL-{i:06d}", move_type=mtype,
                item_id=item_ids[item_i], quantity=Decimal(qty), base_uom_id=uom["id"],
                from_bin_id=bin_["id"] if mtype == "ISSUE" else None,
                to_bin_id=bin_["id"] if mtype == "RECEIPT" else None,
                lot_id=None, serial_id=None, move_date=d, reference="volume seed",
                posted=True, unit_cost=item_costs[item_i],
            )
            doc["doc_id"] = move["id"]
            doc_rows.append(doc)
            move_rows.append(move)
        await bulk(conn, Document.__table__, doc_rows)
        await bulk(conn, StockMove.__table__, move_rows)
        quant_rows = [
            row(item_id=item_ids[i], bin_id=bin_["id"], lot_id=None,
                on_hand_qty=Decimal(on_hand[i]))
            for i in range(V_ITEMS)
        ]
        await bulk(conn, StockQuant.__table__, quant_rows)
        val_rows = [
            row(
                item_id=item_ids[i], warehouse_id=wh["id"], on_hand_qty=Decimal(on_hand[i]),
                avg_unit_cost=item_costs[i], total_value=Decimal(on_hand[i]) * item_costs[i],
            )
            for i in range(V_ITEMS)
        ]
        await bulk(conn, ItemValuation.__table__, val_rows)

        # ── ≥10k sales orders (2 lines each) ─────────────────────────────
        doc_rows, order_rows, line_rows = [], [], []
        for i in range(V_ORDERS):
            d = span_start + timedelta(days=rng.randrange(span_days))
            order = row(
                document_id=None, order_number=f"SO-VOL-{i:06d}", status="CONFIRMED",
                customer_id=customer_ids[i % len(customer_ids)], currency_code="USD",
                order_date=d, requested_date=d + timedelta(days=7), payment_terms_days=30,
                total_amount=Decimal(0), source_quote_id=None,
                credit_check_status="PASSED", notes=None,
            )
            total = Decimal(0)
            for ln in (1, 2):
                item_i = rng.randrange(V_ITEMS)
                qty = Decimal(1 + rng.randrange(10))
                price = item_costs[item_i] * 2
                amount = qty * price
                total += amount
                line_rows.append(
                    row(
                        order_id=order["id"], line_number=ln, item_id=item_ids[item_i],
                        description=None, ordered_quantity=qty, uom_id=uom["id"],
                        unit_price=price, discount_type=None, discount_value=None,
                        line_amount=amount, delivered_quantity=Decimal(0),
                        invoiced_quantity=Decimal(0), returned_quantity=Decimal(0),
                        tax_code_id=None,
                    )
                )
            order["total_amount"] = total
            doc = row(doc_type=SALES_ORDER_DOC_TYPE, doc_id=order["id"],
                      doc_number=f"SO-VOL-{i:06d}", status="CONFIRMED")
            order["document_id"] = doc["id"]
            doc_rows.append(doc)
            order_rows.append(order)
        await bulk(conn, Document.__table__, doc_rows)
        await bulk(conn, SalesOrder.__table__, order_rows)
        await bulk(conn, SalesOrderLine.__table__, line_rows)

        # ── ≥100k journal lines (25 200 posted entries × 4 balanced lines) ──
        doc_rows, entry_rows, jline_rows = [], [], []
        for i in range(V_ENTRIES):
            month_i = i % 30  # 2024-01 .. 2026-06
            year, month = 2024 + month_i // 12, 1 + month_i % 12
            d = date(year, month, 1 + i % 28)
            per_id = period_for(d)
            entry = row(
                document_id=None, entry_number=f"JE-VOL-{i:06d}", posting_date=d,
                fiscal_period_id=per_id, document_type="JOURNAL", currency_code="USD",
                description=f"Volume entry {i}", status="POSTED",
                reverses_entry_id=None, reversed_by_entry_id=None, posted_at=now,
            )
            doc = row(doc_type=JOURNAL_ENTRY_DOC_TYPE, doc_id=entry["id"],
                      doc_number=f"JE-VOL-{i:06d}", status="POSTED")
            entry["document_id"] = doc["id"]
            doc_rows.append(doc)
            entry_rows.append(entry)
            revenue = Decimal(100 + i % 900)
            cost = Decimal(60 + i % 500)
            legs = [  # Dr AR / Cr Revenue + Dr COGS / Cr Inventory — balanced by construction
                ("1100", revenue, True), ("4000", revenue, False),
                ("5000", cost, True), ("1200", cost, False),
            ]
            for ln, (acode, amount, is_debit) in enumerate(legs, start=1):
                jline_rows.append(
                    row(
                        journal_entry_id=entry["id"], line_number=ln,
                        account_id=accounts[acode], description=None,
                        transaction_debit_amount=amount if is_debit else Decimal(0),
                        transaction_credit_amount=Decimal(0) if is_debit else amount,
                        functional_debit_amount=amount if is_debit else Decimal(0),
                        functional_credit_amount=Decimal(0) if is_debit else amount,
                        currency_code="USD", cost_center_id=None, profit_center_id=None,
                        project_id=None, item_id=None, partner_type=None, partner_id=None,
                        is_posted=True, posting_date=d, fiscal_period_id=per_id,
                    )
                )
        await bulk(conn, Document.__table__, doc_rows)
        await bulk(conn, JournalEntry.__table__, entry_rows)
        await bulk(conn, JournalLine.__table__, jline_rows)

    elapsed = time.perf_counter() - t0
    print(
        f"seed --volume: ok in {elapsed:.1f}s — items={V_ITEMS} stock_moves={V_MOVES} "
        f"orders={V_ORDERS} journal_entries={V_ENTRIES} journal_lines={V_ENTRIES * 4} "
        f"fiscal_years=3"
    )


if __name__ == "__main__":
    if "--volume" in sys.argv:
        if _seed_enabled():
            asyncio.run(seed_volume())
    else:
        main()
