"""Menu structure (#212, D-081): the section tree, a dish's placement in it, and its tags.

The rules worth pinning are the ones the DATABASE cannot enforce. A composite FK already says "the
parent is a section in my tenant"; it cannot say that a section may not be moved inside its own
branch, that a menu stops nesting at three levels, or that a heading with dishes still under it
must not be deleted. Those three are the file's spine.

The rest pins the two axes staying independent — moving a dish must not touch its tags, tagging it
must not move it — because collapsing them into one is the design mistake D-081 exists to refuse,
and it would show up first as one write clobbering the other.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import run_in_uow
from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.rbac import catalog_keys
from app.core.tenancy import tenant_context
from app.modules.hospitality import queries
from app.modules.hospitality.menu_models import MenuItemTag, MenuPlacement
from app.modules.hospitality.service import menu


async def _run(
    session: AsyncSession, tenant_id: uuid.UUID, work: Callable[[], Awaitable[object]]
) -> object:
    """Drive a service call inside a uow (D-011/D-025), returning whatever it returned."""
    holder: list[object] = []

    async def _work() -> None:
        holder.append(await work())

    with tenant_context(tenant_id):
        await run_in_uow(session, _work)
    return holder[0]


async def _section(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    name: str,
    parent_id: uuid.UUID | None = None,
    sort_order: int = 0,
) -> uuid.UUID:
    section = await _run(
        session,
        tenant_id,
        lambda: menu.create_section(
            session, tenant_id, name=name, parent_id=parent_id, sort_order=sort_order
        ),
    )
    return section.id  # type: ignore[union-attr]


# --- The tree ------------------------------------------------------------------


async def test_sections_nest_and_read_back_in_the_propertys_own_order(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Desserts come last because the restaurant says so, not because D sorts after M.

    The read is FLAT and the caller nests it by ``parent_id``, so what has to be right is the
    order WITHIN each sibling list — a global order across levels would mean nothing once the
    client nests it anyway."""
    starters = await _section(db_session, tenant_a, "Starters", sort_order=1)
    await _section(db_session, tenant_a, "Desserts", sort_order=3)
    await _section(db_session, tenant_a, "Main courses", sort_order=2)
    await _section(db_session, tenant_a, "Cold", parent_id=starters, sort_order=1)

    with tenant_context(tenant_a):
        sections = await queries.list_sections(db_session, tenant_a)

    roots = [section.name for section in sections if section.parent_id is None]
    assert roots == ["Starters", "Main courses", "Desserts"], (
        "the property's own running order, not alphabetical"
    )
    children = [section for section in sections if section.parent_id == starters]
    assert [section.name for section in children] == ["Cold"]


async def test_a_section_cannot_be_moved_inside_its_own_branch(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The one the database cannot see: both ends are legitimate rows in the right tenant, and the
    move would detach the whole branch — rows still there, reachable from nothing."""
    mains = await _section(db_session, tenant_a, "Main courses")
    grill = await _section(db_session, tenant_a, "Grill", parent_id=mains)

    with pytest.raises(ValidationFailedError) as excinfo:
        await _run(
            db_session,
            tenant_a,
            lambda: menu.update_section(
                db_session, tenant_a, mains, parent_id=grill, reparent=True
            ),
        )
    assert excinfo.value.code == "hospitality.menu_section_cycle"

    with pytest.raises(ValidationFailedError):
        await _run(
            db_session,
            tenant_a,
            lambda: menu.update_section(
                db_session, tenant_a, mains, parent_id=mains, reparent=True
            ),
        )


async def test_a_menu_stops_nesting_at_the_depth_cap(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Three levels is a menu; four is a filing system nothing renders."""
    one = await _section(db_session, tenant_a, "Main courses")
    two = await _section(db_session, tenant_a, "Grill", parent_id=one)
    three = await _section(db_session, tenant_a, "Steaks", parent_id=two)

    with pytest.raises(ValidationFailedError) as excinfo:
        await _section(db_session, tenant_a, "Rare", parent_id=three)
    assert excinfo.value.code == "hospitality.menu_section_too_deep"


async def test_a_section_that_still_holds_something_is_not_deleted(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """Refusing beats cascading: a cascade would silently unplace every dish under a mis-click,
    and the rows it removed carry no way back."""
    starters = await _section(db_session, tenant_a, "Starters")
    cold = await _section(db_session, tenant_a, "Cold", parent_id=starters)

    with pytest.raises(ConflictError) as excinfo:
        await _run(
            db_session, tenant_a, lambda: menu.delete_section(db_session, tenant_a, starters)
        )
    assert excinfo.value.code == "hospitality.menu_section_not_empty"
    assert excinfo.value.details["child_sections"] == 1

    await _run(
        db_session,
        tenant_a,
        lambda: menu.set_placement(db_session, tenant_a, dish_id, section_id=cold, tags=[]),
    )
    with pytest.raises(ConflictError) as excinfo:
        await _run(db_session, tenant_a, lambda: menu.delete_section(db_session, tenant_a, cold))
    assert excinfo.value.details["dishes"] == 1

    # Emptied deliberately, it goes.
    await _run(
        db_session,
        tenant_a,
        lambda: menu.set_placement(db_session, tenant_a, dish_id, section_id=None, tags=[]),
    )
    await _run(db_session, tenant_a, lambda: menu.delete_section(db_session, tenant_a, cold))
    with tenant_context(tenant_a), pytest.raises(NotFoundError):
        await menu.get_section(db_session, tenant_a, cold)


# --- A dish's place, and its labels --------------------------------------------


async def test_a_dish_sits_in_exactly_one_section_and_moving_it_replaces_the_old(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    starters = await _section(db_session, tenant_a, "Starters")
    mains = await _section(db_session, tenant_a, "Main courses")

    await _run(
        db_session,
        tenant_a,
        lambda: menu.set_placement(db_session, tenant_a, dish_id, section_id=starters, tags=[]),
    )
    await _run(
        db_session,
        tenant_a,
        lambda: menu.set_placement(db_session, tenant_a, dish_id, section_id=mains, tags=[]),
    )

    with tenant_context(tenant_a):
        rows = (
            await db_session.execute(
                select(MenuPlacement).where(MenuPlacement.item_id == dish_id)
            )
        ).scalars().all()
    assert len(rows) == 1, "a move must replace the placement, never add a second"
    assert rows[0].section_id == mains


async def test_tags_are_cleaned_deduplicated_and_replaced_as_a_set(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """"Vegan", "vegan " and "VEGAN" are one label — otherwise a filter has to guess which
    spelling a property used on any given night."""
    _, tags = await _run(  # type: ignore[misc]
        db_session,
        tenant_a,
        lambda: menu.set_placement(
            db_session,
            tenant_a,
            dish_id,
            section_id=None,
            tags=["Vegan", "vegan ", " SPICY", "spicy"],
        ),
    )
    assert tags == ["vegan", "spicy"]

    # The set is REPLACED, not merged: dropping a tag drops it.
    _, tags = await _run(  # type: ignore[misc]
        db_session,
        tenant_a,
        lambda: menu.set_placement(
            db_session, tenant_a, dish_id, section_id=None, tags=["spicy", "gluten-free"]
        ),
    )
    assert tags == ["spicy", "gluten-free"]
    with tenant_context(tenant_a):
        stored = (
            await db_session.execute(
                select(MenuItemTag.tag).where(MenuItemTag.item_id == dish_id)
            )
        ).scalars().all()
    assert sorted(stored) == ["gluten-free", "spicy"]


async def test_the_two_axes_are_independent(
    db_session: AsyncSession, tenant_a: uuid.UUID, dish_id: uuid.UUID
) -> None:
    """A dish is Italian AND a main course, and editing one must not clear the other — the whole
    reason D-081 keeps a tree and a flat label set rather than folding either into the other."""
    mains = await _section(db_session, tenant_a, "Main courses")
    await _run(
        db_session,
        tenant_a,
        lambda: menu.set_placement(
            db_session, tenant_a, dish_id, section_id=mains, tags=["italian", "spicy"]
        ),
    )

    with tenant_context(tenant_a):
        placements = await queries.all_placements(db_session, tenant_a)
        tags = await queries.all_tags(db_session, tenant_a)
    assert placements[dish_id] == mains
    assert tags[dish_id] == ["italian", "spicy"]

    with tenant_context(tenant_a):
        tagged = await queries.item_ids_with_tag(db_session, tenant_a, "ITALIAN ")
    assert tagged == [dish_id], "the filter must match the cleaned label, not the typed one"


async def test_an_unknown_dish_cannot_be_placed(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """``item_id`` is an opaque id with no FK (D-029), so this check IS the referential
    integrity — without it a typo becomes a placement pointing at nothing."""
    with pytest.raises(ValidationFailedError) as excinfo:
        await _run(
            db_session,
            tenant_a,
            lambda: menu.set_placement(
                db_session, tenant_a, uuid.uuid4(), section_id=None, tags=["vegan"]
            ),
        )
    assert excinfo.value.code == "hospitality.item_not_found"


async def test_another_tenants_section_is_not_reachable(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    starters = await _section(db_session, tenant_a, "Starters")
    with tenant_context(tenant_b), pytest.raises(NotFoundError):
        await menu.get_section(db_session, tenant_b, starters)

    with tenant_context(tenant_b):
        assert await queries.list_sections(db_session, tenant_b) == []


async def test_the_tree_read_does_not_grow_with_the_menu(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """Two statements for the whole tree — the sections and one grouped count — never a count per
    section, which is the N+1 a tree view invites (PERFORMANCE §2)."""
    for index in range(12):
        await _section(db_session, tenant_a, f"Course {index}", sort_order=index)

    with tenant_context(tenant_a):
        sections = await queries.list_sections(db_session, tenant_a)
        counts = await queries.dish_counts_by_section(db_session, tenant_a)
    assert len(sections) == 12
    assert counts == {}

    with tenant_context(tenant_a):
        total = (
            await db_session.execute(select(func.count()).select_from(MenuPlacement))
        ).scalar_one()
    assert total == 0


# --- Over the wire -------------------------------------------------------------


async def test_the_menu_structure_endpoints_round_trip(hospitality_api) -> None:
    """The manager's whole loop: build a tree, put a dish under a heading, label it, read it
    back — and the two reads the UI and a website actually call."""
    client = hospitality_api.client
    dish_id = hospitality_api.kitchen.dishes["PASTA"]

    created = await client.post(
        "/api/v1/hospitality/menu/sections", json={"name": "Main courses", "sort_order": 2}
    )
    assert created.status_code == 201, created.text
    mains = created.json()["id"]
    child = await client.post(
        "/api/v1/hospitality/menu/sections",
        json={"name": "Italian", "parent_id": mains, "sort_order": 1},
    )
    assert child.status_code == 201, child.text

    placed = await client.put(
        f"/api/v1/hospitality/menu/{dish_id}/placement",
        json={"section_id": child.json()["id"], "tags": ["Italian", "vegan"]},
    )
    assert placed.status_code == 200, placed.text
    assert placed.json()["tags"] == ["italian", "vegan"]

    sections = await client.get("/api/v1/hospitality/menu/sections")
    assert sections.status_code == 200, sections.text
    by_name = {row["name"]: row for row in sections.json()}
    assert by_name["Italian"]["parent_id"] == mains
    assert by_name["Italian"]["dish_count"] == 1
    assert by_name["Main courses"]["dish_count"] == 0, "counts are DIRECT, never cumulative"

    placements = await client.get("/api/v1/hospitality/menu/placements")
    assert placements.status_code == 200, placements.text
    assert placements.json()["items"] == [
        {"item_id": str(dish_id), "section_id": child.json()["id"], "tags": ["italian", "vegan"]}
    ]

    tags = await client.get("/api/v1/hospitality/menu/tags")
    assert tags.json() == ["italian", "vegan"]

    # Renaming leaves the dish where it is; the two axes are edited through one PUT but stored
    # independently.
    renamed = await client.patch(
        f"/api/v1/hospitality/menu/sections/{child.json()['id']}", json={"name": "Pasta"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Pasta"


async def test_menu_structure_writes_need_menu_manage(
    hospitality_api,
    client,
    hospitality_user_factory,
) -> None:
    """Reading the structure is ``menu.read`` — the website credential already holds it, so a site
    can render the menu in the restaurant's own order. WRITING is ``menu.manage``, the same key
    that 86s a dish, so a leaked website key can never rearrange the menu."""
    created = await hospitality_api.client.post(
        "/api/v1/hospitality/menu/sections", json={"name": "Starters"}
    )
    assert created.status_code == 201, created.text

    read_only = tuple(
        key
        for key in sorted(catalog_keys())
        if key.startswith("hospitality.") and key != "hospitality.menu.manage"
    )
    principal = await hospitality_user_factory(
        slug="hsp-menu-read", email="reader@hsp-menu-read.test", keys=read_only
    )
    async with AsyncClient(transport=client._transport, base_url="https://test") as reader:
        token = (
            await reader.post(
                "/api/v1/auth/login",
                json={
                    "tenant_slug": principal.tenant_slug,
                    "email": principal.email,
                    "password": principal.password,
                },
            )
        ).json()["access_token"]
        reader.headers["Authorization"] = f"Bearer {token}"
        assert (await reader.get("/api/v1/hospitality/menu/sections")).status_code == 200
        assert (await reader.get("/api/v1/hospitality/menu/placements")).status_code == 200
        refused = await reader.post(
            "/api/v1/hospitality/menu/sections", json={"name": "Desserts"}
        )
    assert refused.status_code == 403, refused.text
