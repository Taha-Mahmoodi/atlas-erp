"""Hospitality test fixtures (STRUCTURE §6): a menu item to hang availability and tickets off.

A menu item IS an ordinary inventory ``Item`` (PLAN 19 adds no second item entity), so the setup is
two calls into the inventory factories and there is nothing for a hospitality ``factories.py`` to
own yet — these thin fixtures are the whole surface. Promote to ``factories.py`` when Task 6/7 need
a builder that composes more than this.

``build_inventory_setup`` seeds EA and BOX with FIXED codes, so it must run ONCE per tenant; every
dish then comes from ``make_dish``. No GL accounts and no fiscal year are wired: neither
availability nor an order ticket moves stock or posts a journal (ingredient depletion is a separate
BACKGROUND concern, Q4/Task 5).
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import partial

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.modules.hospitality.factories import (
    HospitalityPrincipal,
    Kitchen,
    build_kitchen,
    create_hospitality_principal,
)
from tests.modules.inventory.factories import (
    InventorySetup,
    build_inventory_setup,
    build_item,
)

__all__ = ["HospitalityPrincipal", "InventorySetup", "Kitchen"]


@pytest.fixture
async def menu_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> InventorySetup:
    """EA/BOX units and a category — the minimum a sellable item needs."""
    return await build_inventory_setup(db_session, tenant_a)


@pytest.fixture
def make_dish(
    db_session: AsyncSession, tenant_a: uuid.UUID, menu_setup: InventorySetup
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Create one sellable menu item and return its id. Ids rather than ORM objects: a ticket test
    commits repeatedly, and an expired instance would fail on attribute access."""

    async def _make(item_code: str, name: str) -> uuid.UUID:
        item = await build_item(
            db_session,
            tenant_a,
            item_code=item_code,
            category_id=menu_setup.category_id,
            base_uom_id=menu_setup.ea_uom_id,
            name=name,
        )
        return item.id

    return _make


@pytest.fixture
async def dish_id(make_dish: Callable[..., Awaitable[uuid.UUID]]) -> uuid.UUID:
    """The single dish most tests need."""
    return await make_dish("DISH-001", "Caprese")


# --- Hospitality-permissioned HTTP clients (Task 6) ---------------------------
# No autouse handler-registration fixture here: the API tests drive the real app, whose factory
# already calls ``register_event_handlers``. The SERVICE-level depletion tests register their own.


@pytest.fixture
def hospitality_user_factory(
    db_session: AsyncSession,
) -> Callable[..., "Awaitable[HospitalityPrincipal]"]:
    """Provision a tenant + user and grant a role with the hospitality permission keys through the
    real services (D-025). ``keys`` lets a test request a narrower grant (the 403 RBAC tests)."""
    return partial(create_hospitality_principal, db_session)


async def _login(client: AsyncClient, principal: HospitalityPrincipal) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@dataclass(frozen=True)
class HospitalityApi:
    """A logged-in full-rights staff client plus the kitchen seeded in THAT client's tenant, so the
    staff endpoints can be driven over the wire against a property with a real menu."""

    client: AsyncClient
    tenant_id: uuid.UUID
    kitchen: Kitchen


# Ten of every ingredient, against recipes chosen so the at-risk arithmetic has one dish that is
# comfortably coverable, one that cannot be made at all, and one with no recipe to explode.
API_KITCHEN_STOCK = Decimal(10)
API_KITCHEN_RECIPES: dict[str, dict[str, Decimal]] = {
    "PASTA": {"TOMATO": Decimal(2), "BASIL": Decimal(1)},  # min(10//2, 10//1) = 5
    "STEAK": {"BEEF": Decimal(20)},  # 10 // 20 = 0
    "BEER": {},  # a bottled item: no BOM, never on the at-risk list
}


@pytest.fixture
async def hospitality_api(
    client: AsyncClient,
    db_session: AsyncSession,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> AsyncIterator[HospitalityApi]:
    """A bearer-token client holding every hospitality key, with a stocked kitchen (dishes, recipes
    and storeroom stock) seeded in that principal's tenant."""
    principal = await hospitality_user_factory()
    kitchen = await build_kitchen(
        db_session, principal.tenant_id, API_KITCHEN_RECIPES, stock=API_KITCHEN_STOCK
    )
    access_token = await _login(client, principal)
    client.headers["Authorization"] = f"Bearer {access_token}"
    yield HospitalityApi(client=client, tenant_id=principal.tenant_id, kitchen=kitchen)
