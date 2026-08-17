"""Menu-structure HTTP layer (#212, D-081): the section tree, a dish's placement, the tag list.

A THIRD hospitality router, on the same ``/api/v1/hospitality`` prefix as the other two (the
``reservation_router`` precedent). It is separate because it is a separate audience and a separate
cache story: this is the property SETTING UP its menu — slow-changing structure edited by a
manager — while ``router.py`` is the floor mid-service and ``website_router.py`` is a machine.

RBAC reuses the existing menu keys rather than inventing more (D-009): reading the structure is
``menu.read``, which the website credential already holds so a site can render the menu in the
restaurant's own order; editing it is ``menu.manage``, the same key that 86s a dish. A section is
menu state, not a new kind of thing to be permissioned.

No idempotency keys: none of these create a document or claim a number, and every write is a
replace (PUT placement) or refused twice over (a duplicate section name is a unique violation).
"""

import uuid

from fastapi import APIRouter, Depends, Response

from app.core.deps import CurrentUserDep, SessionDep
from app.core.events import run_in_uow
from app.core.rbac import require_permission
from app.modules.hospitality import queries
from app.modules.hospitality.constants import (
    HOSPITALITY_MENU_MANAGE,
    HOSPITALITY_MENU_READ,
)
from app.modules.hospitality.menu_schemas import (
    MenuPlacementRead,
    MenuPlacementSet,
    MenuPlacementsRead,
    MenuSectionCreate,
    MenuSectionRead,
    MenuSectionUpdate,
)
from app.modules.hospitality.service import menu

router = APIRouter(prefix="/api/v1/hospitality", tags=["hospitality-menu"])

_MenuReadGuard = Depends(require_permission(HOSPITALITY_MENU_READ))
_MenuManageGuard = Depends(require_permission(HOSPITALITY_MENU_MANAGE))


@router.get("/menu/sections", response_model=list[MenuSectionRead], dependencies=[_MenuReadGuard])
async def list_menu_sections(
    current: CurrentUserDep, session: SessionDep
) -> list[MenuSectionRead]:
    """The whole tree in the property's running order, each heading with its DIRECT dish count.

    TWO statements whatever the menu's size (PERFORMANCE §2): the sections, then one grouped count
    over placements. A flat list rather than a nested one — the client nests by ``parent_id``,
    which keeps the wire shape stable when a third level appears and means one array to diff.

    Unpaginated, like the reservation grid: a menu's headings are tens of rows and a tree split
    across pages is a tree the caller has to stitch back together.
    """
    sections = await queries.list_sections(session, current.tenant_id)
    counts = await queries.dish_counts_by_section(session, current.tenant_id)
    return [
        MenuSectionRead(
            id=section.id,
            name=section.name,
            parent_id=section.parent_id,
            sort_order=section.sort_order,
            dish_count=counts.get(section.id, 0),
        )
        for section in sections
    ]


@router.post(
    "/menu/sections",
    response_model=MenuSectionRead,
    status_code=201,
    dependencies=[_MenuManageGuard],
)
async def create_menu_section(
    payload: MenuSectionCreate, current: CurrentUserDep, session: SessionDep
) -> MenuSectionRead:
    """Add a heading. Refused if it would nest deeper than the menu allows."""
    holder: dict[str, MenuSectionRead] = {}

    async def work() -> None:
        section = await menu.create_section(
            session,
            current.tenant_id,
            name=payload.name,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
        )
        await session.refresh(section)
        holder["read"] = MenuSectionRead.model_validate(section)

    await run_in_uow(session, work)
    return holder["read"]


@router.patch(
    "/menu/sections/{section_id}",
    response_model=MenuSectionRead,
    dependencies=[_MenuManageGuard],
)
async def update_menu_section(
    section_id: uuid.UUID,
    payload: MenuSectionUpdate,
    current: CurrentUserDep,
    session: SessionDep,
) -> MenuSectionRead:
    """Rename, reorder, or move a heading. Moving it inside its own branch is refused
    (``hospitality.menu_section_cycle``) — the database cannot see that one."""
    holder: dict[str, MenuSectionRead] = {}

    async def work() -> None:
        section = await menu.update_section(
            session,
            current.tenant_id,
            section_id,
            name=payload.name,
            parent_id=payload.parent_id,
            reparent=payload.reparent,
            sort_order=payload.sort_order,
        )
        await session.refresh(section)
        holder["read"] = MenuSectionRead.model_validate(section)

    await run_in_uow(session, work)
    return holder["read"]


@router.delete(
    "/menu/sections/{section_id}", status_code=204, dependencies=[_MenuManageGuard]
)
async def delete_menu_section(
    section_id: uuid.UUID, current: CurrentUserDep, session: SessionDep
) -> Response:
    """Remove an EMPTY heading. Refused while dishes or sub-sections still hang off it
    (409 ``hospitality.menu_section_not_empty``) rather than cascading them into nothing."""

    async def work() -> None:
        await menu.delete_section(session, current.tenant_id, section_id)

    await run_in_uow(session, work)
    return Response(status_code=204)


@router.get(
    "/menu/placements", response_model=MenuPlacementsRead, dependencies=[_MenuReadGuard]
)
async def list_menu_placements(
    current: CurrentUserDep, session: SessionDep
) -> MenuPlacementsRead:
    """Every placed or tagged dish: which section it sits in and what it is labelled.

    TWO statements plus auth, flat in the menu's size — the placements, then the tags — which is
    the budget this read exists to respect. `GET /menu` stays at its own three (see
    ``MenuPlacementsRead``): structure, price and availability change on three different clocks
    and are three resources on purpose.

    Unpaginated for the same reason the section tree is: the answer is bounded by the number of
    dishes a kitchen cooks, and a map split across pages is a map the caller has to reassemble
    before it can render anything.
    """
    placements = await queries.all_placements(session, current.tenant_id)
    tags = await queries.all_tags(session, current.tenant_id)
    item_ids = sorted(set(placements) | set(tags), key=str)
    return MenuPlacementsRead(
        items=[
            MenuPlacementRead(
                item_id=item_id, section_id=placements.get(item_id), tags=tags.get(item_id, [])
            )
            for item_id in item_ids
        ]
    )


@router.get("/menu/tags", response_model=list[str], dependencies=[_MenuReadGuard])
async def list_menu_tags(current: CurrentUserDep, session: SessionDep) -> list[str]:
    """Every tag the property has actually used, alphabetical — the picker's options, computed
    from the labels in use rather than kept in a master table somebody has to prune (D-081)."""
    return await queries.tags_in_use(session, current.tenant_id)


@router.put(
    "/menu/{item_id}/placement",
    response_model=MenuPlacementRead,
    dependencies=[_MenuManageGuard],
)
async def set_menu_placement(
    item_id: uuid.UUID,
    payload: MenuPlacementSet,
    current: CurrentUserDep,
    session: SessionDep,
) -> MenuPlacementRead:
    """Put a dish under a heading and label it — both REPLACED together.

    PUT because it replaces the dish's whole menu placement: re-sending the same body is the same
    state, which is what makes it safe to retry without a key. ``section_id: null`` takes the dish
    off the menu structure without touching the item, its price or its availability.
    """
    holder: dict[str, MenuPlacementRead] = {}

    async def work() -> None:
        section_id, tags = await menu.set_placement(
            session,
            current.tenant_id,
            item_id,
            section_id=payload.section_id,
            tags=payload.tags,
        )
        holder["read"] = MenuPlacementRead(item_id=item_id, section_id=section_id, tags=tags)

    await run_in_uow(session, work)
    return holder["read"]
