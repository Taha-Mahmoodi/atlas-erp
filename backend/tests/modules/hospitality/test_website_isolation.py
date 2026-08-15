"""Adversarial probes: idempotency and tenant isolation on the Phase 19 website surface.

The website is the one caller Atlas does not control. It authenticates as a D-069 machine
credential, it retries on every timeout with the same ``Idempotency-Key``, and its request bodies
carry ids a guest's browser could have typed. Everything below tries to make that produce a second
ticket, a second depletion of the same stock, or a row belonging to another property.

Three groups:

1. **Replay.** Same key twice, same key with a different body, two keys with the same order, and a
   replayed FIRE — the endpoint whose retry would cook the order twice.
2. **Isolation.** TWO properties, each with its own credential, probed against each other: menu,
   86 board, tickets, and an order line naming the rival's item. The ordinary D-007 predicate on
   each query is what has to stop every one of them, and the reservation PK's leading ``tenant_id``
   is what stops a replay crossing.
3. **The shared principal namespace** (Phase 18's recorded limit, ``tests/core/
   test_api_key_concurrency.py``): ``core_idempotency_keys`` has no principal column, so a staff
   terminal and the website meet on one row. Recorded here on the endpoint this phase adds, with
   what bounds it.

Both properties are built by ``_property`` rather than reusing the ``website_api`` fixture, because
every probe here needs BOTH credentials for one tenant — the machine key and a staff login — and
the fixture exposes only the key.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs import Job, wait_for_jobs
from app.core.tenancy import tenant_context
from app.modules.hospitality.constants import DEPLETE_TICKET_JOB, OrderTicketStatus
from app.modules.hospitality.models import OrderTicket
from tests.modules.hospitality.conftest import (
    API_KITCHEN_RECIPES,
    API_KITCHEN_STOCK,
    MENU_PRICES,
    HospitalityApi,
)
from tests.modules.hospitality.factories import (
    HospitalityPrincipal,
    Kitchen,
    build_dish,
    build_kitchen,
    build_menu_price,
    build_menu_price_list,
    mint_website_key,
    seed_menu_currency,
)

MENU_URL = "/api/v1/hospitality/menu"
AVAILABILITY_URL = "/api/v1/hospitality/menu/availability"
ORDERS_URL = "/api/v1/hospitality/orders"
TICKETS_URL = "/api/v1/hospitality/tickets"


def _order(item_id: uuid.UUID, quantity: str = "1") -> dict[str, object]:
    return {"table_code": "WEB", "lines": [{"item_id": str(item_id), "quantity": quantity}]}


def _idem(key: str) -> dict[str, str]:
    return {"Idempotency-Key": key}


def _auth(credential: str) -> dict[str, str]:
    """Per-request Authorization — an API key and a staff JWT are both bearer credentials, so one
    client drives both principals and the header decides which one a request presents."""
    return {"Authorization": f"Bearer {credential}"}


@dataclass(frozen=True)
class Property:
    """One restaurant: its tenant, its priced menu and stocked storeroom, its website credential
    and a staff bearer token on the same user."""

    tenant_id: uuid.UUID
    kitchen: Kitchen
    key: str
    token: str


async def _property(
    client: AsyncClient,
    session: AsyncSession,
    factory: Callable[..., Awaitable[HospitalityPrincipal]],
    *,
    slug: str,
) -> Property:
    """The ``website_api`` fixture's setup reduced to what an isolation probe needs, callable twice
    so two properties exist in one test, and returning the staff token as well as the key."""
    principal = await factory(slug=slug, email=f"web@{slug}.test")
    kitchen = await build_kitchen(
        session, principal.tenant_id, API_KITCHEN_RECIPES, stock=API_KITCHEN_STOCK
    )
    await seed_menu_currency(session, principal.tenant_id)
    price_list_id = await build_menu_price_list(session, principal.tenant_id)
    for dish_code, price in MENU_PRICES.items():
        await build_menu_price(
            session, principal.tenant_id, price_list_id, kitchen.dishes[dish_code], str(price)
        )
    login = await client.post(
        "/api/v1/auth/login",
        json={
            "tenant_slug": principal.tenant_slug,
            "email": principal.email,
            "password": principal.password,
        },
    )
    assert login.status_code == 200, login.text
    return Property(
        tenant_id=principal.tenant_id,
        kitchen=kitchen,
        key=await mint_website_key(session, principal),
        token=login.json()["access_token"],
    )


@pytest.fixture
async def one(
    client: AsyncClient,
    db_session: AsyncSession,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> Property:
    return await _property(client, db_session, hospitality_user_factory, slug="hsp-one")


@pytest.fixture
async def two(
    client: AsyncClient,
    db_session: AsyncSession,
    hospitality_user_factory: Callable[..., Awaitable[HospitalityPrincipal]],
) -> Property:
    """The rival property next door — same menu codes, entirely different ids."""
    return await _property(client, db_session, hospitality_user_factory, slug="hsp-two")


async def _ticket_count(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    with tenant_context(tenant_id):
        await session.commit()  # see what the request's own session committed
        return (
            await session.execute(
                select(func.count(OrderTicket.id)).where(OrderTicket.tenant_id == tenant_id)
            )
        ).scalar_one()


async def _jobs(session: AsyncSession, tenant_id: uuid.UUID) -> list[Job]:
    with tenant_context(tenant_id):
        await session.commit()
        rows = await session.execute(
            select(Job).where(Job.tenant_id == tenant_id, Job.job_type == DEPLETE_TICKET_JOB)
        )
        return list(rows.scalars().all())


# --- 1. Replay ----------------------------------------------------------------


async def test_a_replayed_order_repeats_the_ids_and_submits_no_second_job(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """The retry the website WILL send. Everything about the second response has to be the first
    one verbatim — same ticket id, same gapless number — and the second attempt must leave no trace
    in the tenant: one ticket row, one depletion job against the same stock."""
    body = _order(one.kitchen.dishes["PASTA"], "3")
    key = str(uuid.uuid4())

    first = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.key)})
    assert first.status_code == 201, first.text
    await wait_for_jobs()
    after_first = {job.id for job in await _jobs(db_session, one.tenant_id)}

    second = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.key)})
    assert second.status_code == 201, second.text
    assert second.headers.get("Idempotency-Replayed") == "true"
    assert second.json() == first.json()  # verbatim, gapless ticket_number included

    await wait_for_jobs()
    assert {job.id for job in await _jobs(db_session, one.tenant_id)} == after_first
    assert await _ticket_count(db_session, one.tenant_id) == 1


async def test_the_same_key_with_a_different_order_is_refused_and_cooks_nothing(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """A client bug (or an attacker) sending a SECOND, different order under a spent key must be
    served neither by executing it nor by replaying the first order's answer."""
    key = str(uuid.uuid4())
    first = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["PASTA"]),
        headers={**_idem(key), **_auth(one.key)},
    )
    assert first.status_code == 201, first.text

    second = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["BEER"], "9"),
        headers={**_idem(key), **_auth(one.key)},
    )
    assert second.status_code == 422, second.text
    assert second.json()["error"]["code"] == "idempotency.key_reuse"
    assert await _ticket_count(db_session, one.tenant_id) == 1


async def test_two_keys_for_the_same_order_are_two_tickets(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """The legitimate double: two guests ordering the same dish, or one ordering twice. The key is
    the ONLY thing that makes a request a retry, so distinct keys must both be served."""
    body = _order(one.kitchen.dishes["PASTA"])

    first = await client.post(
        ORDERS_URL, json=body, headers={**_idem(str(uuid.uuid4())), **_auth(one.key)}
    )
    second = await client.post(
        ORDERS_URL, json=body, headers={**_idem(str(uuid.uuid4())), **_auth(one.key)}
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["ticket_id"] != second.json()["ticket_id"]
    assert first.json()["ticket_number"] != second.json()["ticket_number"]

    await wait_for_jobs()
    assert len(await _jobs(db_session, one.tenant_id)) == 2
    assert await _ticket_count(db_session, one.tenant_id) == 2


async def _open_ticket(api: HospitalityApi, table_code: str) -> str:
    response = await api.client.post(
        TICKETS_URL,
        json={
            "table_code": table_code,
            "lines": [
                {
                    "item_id": str(api.kitchen.dishes["PASTA"]),
                    "quantity": "1",
                    "unit_price": "18.00",
                }
            ],
        },
        headers=_idem(str(uuid.uuid4())),
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_a_replayed_fire_does_not_deplete_twice(
    hospitality_api: HospitalityApi, db_session: AsyncSession
) -> None:
    """The staff half of the same retry. Firing is the commitment moment (Q4), so a terminal
    retrying a timed-out fire must get the first answer rather than submit a second depletion."""
    ticket_id = await _open_ticket(hospitality_api, "T1")
    key = str(uuid.uuid4())

    fire = await hospitality_api.client.post(f"{TICKETS_URL}/{ticket_id}/fire", headers=_idem(key))
    assert fire.status_code == 200, fire.text
    again = await hospitality_api.client.post(
        f"{TICKETS_URL}/{ticket_id}/fire", headers=_idem(key)
    )
    assert again.status_code == 200, again.text
    assert again.headers.get("Idempotency-Replayed") == "true"
    assert again.json() == fire.json()

    await wait_for_jobs()
    assert len(await _jobs(db_session, hospitality_api.tenant_id)) == 1


async def test_a_fire_key_spent_on_one_ticket_cannot_answer_for_another(
    hospitality_api: HospitalityApi, db_session: AsyncSession
) -> None:
    """A fire carries NO body, so D-013's hash of an empty body is identical for every ticket on
    the route and the "different body -> 422 key_reuse" defence cannot fire. If the reservation
    does not also cover WHICH ticket was addressed, a terminal that reuses a key across two tables
    gets a 200 for a check still sitting OPEN that never reaches the kitchen: food nobody cooks,
    reported as sent.
    """
    first_id = await _open_ticket(hospitality_api, "T1")
    second_id = await _open_ticket(hospitality_api, "T2")
    key = str(uuid.uuid4())

    first = await hospitality_api.client.post(
        f"{TICKETS_URL}/{first_id}/fire", headers=_idem(key)
    )
    assert first.status_code == 200, first.text

    second = await hospitality_api.client.post(
        f"{TICKETS_URL}/{second_id}/fire", headers=_idem(key)
    )
    assert second.json().get("id") != first_id, (
        "reusing a fire key on a SECOND ticket replayed the FIRST ticket's response: "
        f"{second.status_code} {second.text}"
    )
    # The request TARGET is hashed with the body (core/idempotency), so the spent key now reads as
    # what it is — a key reused for a different request — and the answer is a loud 422 the terminal
    # retries under a fresh key. Refusing is the right half of the pair: the WRONG outcome is a 200
    # for a ticket nobody cooked.
    assert second.status_code == 422, second.text
    assert second.json()["error"]["code"] == "idempotency.key_reuse"

    state = await hospitality_api.client.get(f"{TICKETS_URL}/{second_id}")
    assert state.status_code == 200, state.text
    assert state.json()["status"] == OrderTicketStatus.OPEN.value
    await wait_for_jobs()
    assert len(await _jobs(db_session, hospitality_api.tenant_id)) == 1


async def test_one_key_value_spans_the_website_and_staff_endpoints_independently(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """D-013 scopes a reservation per ENDPOINT, and the website order deliberately does not reuse
    the staff create's endpoint string. A guest's browser and a terminal that happen to mint the
    same key value must therefore not collide — one is an order, the other opens a check."""
    key = str(uuid.uuid4())

    web = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["PASTA"]),
        headers={**_idem(key), **_auth(one.key)},
    )
    assert web.status_code == 201, web.text

    staff = await client.post(
        TICKETS_URL,
        json={
            "table_code": "T9",
            "lines": [
                {
                    "item_id": str(one.kitchen.dishes["BEER"]),
                    "quantity": "2",
                    "unit_price": "6.00",
                }
            ],
        },
        headers={**_idem(key), **_auth(one.token)},
    )
    assert staff.status_code == 201, staff.text
    assert staff.json()["id"] != web.json()["ticket_id"]
    assert await _ticket_count(db_session, one.tenant_id) == 2


# --- 2. Tenant isolation ------------------------------------------------------


async def test_a_website_key_never_sees_the_other_propertys_menu(
    client: AsyncClient, db_session: AsyncSession, one: Property, two: Property
) -> None:
    """The read a guest hits first. A key is bound to ONE tenant (its prefix carries the tenant ref
    and the row is then read under that D-007 context), so the rival's dishes cannot appear."""
    secret = await build_dish(
        db_session, one.tenant_id, one.kitchen.setup, item_code="SECRET", recipe={}
    )

    mine = await client.get(MENU_URL, params={"limit": 200}, headers=_auth(one.key))
    theirs = await client.get(MENU_URL, params={"limit": 200}, headers=_auth(two.key))
    assert mine.status_code == 200, mine.text
    assert theirs.status_code == 200, theirs.text

    my_ids = {row["item_id"] for row in mine.json()["items"]}
    their_ids = {row["item_id"] for row in theirs.json()["items"]}
    assert str(secret) in my_ids
    assert not my_ids & their_ids
    assert str(two.kitchen.dishes["PASTA"]) not in my_ids


async def test_a_website_key_never_sees_the_other_propertys_86_board(
    client: AsyncClient, one: Property, two: Property
) -> None:
    """The 86 board and its validator. Two probes: the rival's rows are absent from the body, and
    a cross-tenant 304 is impossible — one property revalidating with the other's ETag must be
    served its OWN board, or a cached copy of the neighbour's would stand in for it."""
    eighty_six = await client.put(
        f"{MENU_URL}/{one.kitchen.dishes['PASTA']}/availability",
        json={"state": "EIGHTY_SIXED", "reason": "out of basil"},
        headers=_auth(one.token),
    )
    assert eighty_six.status_code == 200, eighty_six.text

    mine = await client.get(AVAILABILITY_URL, headers=_auth(one.key))
    theirs = await client.get(AVAILABILITY_URL, headers=_auth(two.key))
    assert mine.status_code == 200 and theirs.status_code == 200
    assert [row["item_id"] for row in mine.json()["items"]] == [str(one.kitchen.dishes["PASTA"])]
    assert theirs.json()["items"] == []
    assert theirs.headers["etag"] != mine.headers["etag"]

    cross = await client.get(
        AVAILABILITY_URL,
        headers={**_auth(two.key), "If-None-Match": mine.headers["etag"]},
    )
    assert cross.status_code == 200, cross.text
    assert cross.json()["items"] == []


async def test_an_order_cannot_reference_another_propertys_item(
    client: AsyncClient, db_session: AsyncSession, one: Property, two: Property
) -> None:
    """The id in the body is the one thing a guest's browser can type. A rival's item id — a real
    row, in the wrong tenant — must not be sellable, and a mixed order must fail WHOLE rather than
    quietly drop the foreign line."""
    foreign = await client.post(
        ORDERS_URL,
        json=_order(two.kitchen.dishes["PASTA"]),
        headers={**_idem(str(uuid.uuid4())), **_auth(one.key)},
    )
    assert foreign.status_code == 422, foreign.text
    assert foreign.json()["error"]["code"] == "hospitality.item_not_priced"

    mixed = await client.post(
        ORDERS_URL,
        json={
            "lines": [
                {"item_id": str(one.kitchen.dishes["PASTA"]), "quantity": "1"},
                {"item_id": str(two.kitchen.dishes["BEER"]), "quantity": "1"},
            ]
        },
        headers={**_idem(str(uuid.uuid4())), **_auth(one.key)},
    )
    assert mixed.status_code == 422, mixed.text
    assert await _ticket_count(db_session, one.tenant_id) == 0
    assert await _ticket_count(db_session, two.tenant_id) == 0


async def test_an_order_cannot_name_the_tenant_it_lands_in(
    client: AsyncClient, db_session: AsyncSession, one: Property, two: Property
) -> None:
    """There is no tenant parameter anywhere on this surface to attack: the credential fixes it
    (``_authenticate_api_key`` sets the D-007 context from the key's own tenant ref before the key
    row is even read). A body field is refused outright — ``WebsiteOrderCreate`` forbids extras —
    and a header the app never reads changes nothing."""
    named = await client.post(
        ORDERS_URL,
        json={
            "tenant_id": str(two.tenant_id),
            "lines": [{"item_id": str(one.kitchen.dishes["PASTA"]), "quantity": "1"}],
        },
        headers={**_idem(str(uuid.uuid4())), **_auth(one.key)},
    )
    assert named.status_code == 422, named.text

    smuggled = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["PASTA"]),
        headers={
            **_idem(str(uuid.uuid4())),
            **_auth(one.key),
            "X-Tenant-Id": str(two.tenant_id),
            "X-Tenant-Slug": "hsp-two",
        },
    )
    assert smuggled.status_code == 201, smuggled.text
    assert await _ticket_count(db_session, one.tenant_id) == 1
    assert await _ticket_count(db_session, two.tenant_id) == 0


async def test_a_refused_order_leaves_its_key_retryable(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """A website's retry loop keeps ONE key per order for as long as it keeps trying. So a refusal
    must not burn the key: the 86 refusal is raised deep inside the fire's uow, and D-013's
    fail-closed teardown has to delete the reservation committed in its own session — otherwise the
    guest who waits for the kitchen to un-86 the dish is answered 422 key_reuse forever."""
    key = str(uuid.uuid4())
    body = _order(one.kitchen.dishes["PASTA"])
    availability_url = f"{MENU_URL}/{one.kitchen.dishes['PASTA']}/availability"

    assert (
        await client.put(
            availability_url,
            json={"state": "EIGHTY_SIXED", "reason": "out of basil"},
            headers=_auth(one.token),
        )
    ).status_code == 200
    refused = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.key)})
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "hospitality.item_unavailable"
    assert await _ticket_count(db_session, one.tenant_id) == 0

    assert (await client.delete(availability_url, headers=_auth(one.token))).status_code == 204
    retried = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.key)})
    assert retried.status_code == 201, retried.text
    assert retried.headers.get("Idempotency-Replayed") is None
    assert await _ticket_count(db_session, one.tenant_id) == 1


async def test_a_staff_ticket_cannot_reference_another_propertys_item(
    client: AsyncClient, db_session: AsyncSession, one: Property, two: Property
) -> None:
    """The staff shape carries its own ``unit_price``, so the price resolution that stops the
    website order above never runs — the batched item-existence validator is what has to catch it,
    which makes this the test that it kept its tenant predicate."""
    response = await client.post(
        TICKETS_URL,
        json={
            "lines": [
                {
                    "item_id": str(two.kitchen.dishes["PASTA"]),
                    "quantity": "1",
                    "unit_price": "0.01",
                }
            ]
        },
        headers={**_idem(str(uuid.uuid4())), **_auth(one.token)},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "hospitality.item_not_found"
    assert await _ticket_count(db_session, one.tenant_id) == 0


async def test_a_property_cannot_read_or_fire_the_other_propertys_ticket(
    client: AsyncClient, one: Property, two: Property
) -> None:
    """A ticket id is an opaque value the order response hands out, so a rival holding one must get
    404 on every ticket route — read, lines, settle, fire — and see nothing in the list."""
    order = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["PASTA"]),
        headers={**_idem(str(uuid.uuid4())), **_auth(one.key)},
    )
    assert order.status_code == 201, order.text
    ticket_id = order.json()["ticket_id"]

    for method, url in (
        ("get", f"{TICKETS_URL}/{ticket_id}"),
        ("get", f"{TICKETS_URL}/{ticket_id}/lines"),
        ("post", f"{TICKETS_URL}/{ticket_id}/settle"),
    ):
        response = await getattr(client, method)(url, headers=_auth(two.token))
        assert response.status_code == 404, f"{method} {url}: {response.text}"

    fire = await client.post(
        f"{TICKETS_URL}/{ticket_id}/fire",
        headers={**_idem(str(uuid.uuid4())), **_auth(two.token)},
    )
    assert fire.status_code == 404, fire.text

    listed = await client.get(TICKETS_URL, headers=_auth(two.token))
    assert listed.status_code == 200, listed.text
    assert listed.json()["items"] == []


async def test_the_idempotency_namespace_does_not_cross_tenants(
    client: AsyncClient, db_session: AsyncSession, one: Property, two: Property
) -> None:
    """The reservation PK leads with ``tenant_id``, so two properties minting the same key value on
    the same endpoint hold two independent reservations — otherwise one property's order would
    replay as the other's, which is a cross-tenant document read."""
    key = "web-0001"

    mine = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["PASTA"]),
        headers={**_idem(key), **_auth(one.key)},
    )
    theirs = await client.post(
        ORDERS_URL,
        json=_order(two.kitchen.dishes["PASTA"]),
        headers={**_idem(key), **_auth(two.key)},
    )
    assert mine.status_code == 201, mine.text
    assert theirs.status_code == 201, theirs.text
    assert mine.json()["ticket_id"] != theirs.json()["ticket_id"]
    assert await _ticket_count(db_session, one.tenant_id) == 1
    assert await _ticket_count(db_session, two.tenant_id) == 1


# --- 3. The shared principal namespace (Phase 18's recorded limit) -------------


async def test_a_staff_principal_shares_the_websites_key_namespace(
    client: AsyncClient, db_session: AsyncSession, one: Property
) -> None:
    """``core_idempotency_keys`` has no principal column, so on THIS phase's order endpoint a staff
    JWT and the website's key share one namespace (``tests/core/test_api_key_concurrency.py``
    records the same at core level). What it costs here: a staff user presenting the website's key
    with the same body gets the website's ticket replayed and creates nothing, and with a different
    body is refused 422 — inside one tenant, bounded by RBAC (the route's permission guard is
    solved before the idempotency guard), and never a cross-tenant read.
    """
    key = str(uuid.uuid4())
    body = _order(one.kitchen.dishes["PASTA"])

    web = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.key)})
    assert web.status_code == 201, web.text

    replayed = await client.post(ORDERS_URL, json=body, headers={**_idem(key), **_auth(one.token)})
    assert replayed.status_code == 201, replayed.text
    assert replayed.headers.get("Idempotency-Replayed") == "true"
    assert replayed.json()["ticket_id"] == web.json()["ticket_id"]

    blocked = await client.post(
        ORDERS_URL,
        json=_order(one.kitchen.dishes["BEER"]),
        headers={**_idem(key), **_auth(one.token)},
    )
    assert blocked.status_code == 422, blocked.text
    assert blocked.json()["error"]["code"] == "idempotency.key_reuse"

    assert await _ticket_count(db_session, one.tenant_id) == 1
    assert Decimal(web.json()["total_amount"]) == MENU_PRICES["PASTA"]
