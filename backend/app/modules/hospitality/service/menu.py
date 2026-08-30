"""Menu structure: the section tree, a dish's place in it, and its tags (#212, D-081).

Every rule that makes the tree a tree lives here — depth, cycles, and what a delete may take with
it — because the database can enforce "the parent is a section in my tenant" and nothing more.

Reads are in ``queries.py`` with the module's other reads; this file is writes plus the two
helpers those writes need.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.modules.hospitality.models import (
    MAX_SECTION_DEPTH,
    MenuItemTag,
    MenuPlacement,
    MenuSection,
)
from app.modules.inventory import queries as inventory_queries

# A tag is stored lower-cased and trimmed, so "Vegan", "vegan " and "vegan" are one label rather
# than three that a filter would have to guess between.
MAX_TAGS_PER_ITEM = 12


async def get_section(
    session: AsyncSession, tenant_id: uuid.UUID, section_id: uuid.UUID
) -> MenuSection:
    """The section, or 404 ``hospitality.menu_section_not_found``."""
    section = await session.get(MenuSection, section_id)
    if section is None or section.tenant_id != tenant_id:
        raise NotFoundError(
            message="Menu section not found", code="hospitality.menu_section_not_found"
        )
    return section


async def _ancestors(
    session: AsyncSession, tenant_id: uuid.UUID, section_id: uuid.UUID
) -> list[uuid.UUID]:
    """The chain from ``section_id`` up to its root, nearest first.

    Walked one hop at a time rather than by recursive CTE on purpose: the walk is bounded by
    ``MAX_SECTION_DEPTH`` (3), so it is at most three cheap primary-key reads on a write path,
    against a CTE that has to be written twice for two dialects. The loop CANNOT run away — it
    stops at the depth cap even if a cycle somehow existed, which is what makes it safe to use in
    the very check that prevents cycles.
    """
    chain: list[uuid.UUID] = []
    current = section_id
    for _ in range(MAX_SECTION_DEPTH + 1):
        parent_id = (
            await session.execute(
                select(MenuSection.parent_id).where(
                    MenuSection.tenant_id == tenant_id, MenuSection.id == current
                )
            )
        ).scalar_one_or_none()
        if parent_id is None:
            return chain
        chain.append(parent_id)
        current = parent_id
    return chain


async def _require_placeable(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    parent_id: uuid.UUID | None,
    moving: uuid.UUID | None,
) -> None:
    """Refuse a parent that would exceed the depth cap or close a cycle.

    ``moving`` is the section being reparented (None when creating), and it is the whole reason
    this is not just a depth check: making a section a child of its own descendant detaches that
    whole branch from the tree — every read that walks up from a dish would spin, and the rows
    would still be there, invisible. The database cannot see it (both ends are legitimate rows in
    the right tenant), so it is refused here.
    """
    if parent_id is None:
        return
    parent = await get_section(session, tenant_id, parent_id)
    ancestors = await _ancestors(session, tenant_id, parent.id)
    if moving is not None and (parent.id == moving or moving in ancestors):
        raise ValidationFailedError(
            message="A section cannot be moved inside itself",
            code="hospitality.menu_section_cycle",
            details={"section_id": str(moving), "parent_id": str(parent_id)},
        )
    # depth of the new parent (root == 1) + the section itself
    if len(ancestors) + 2 > MAX_SECTION_DEPTH:
        raise ValidationFailedError(
            message=f"A menu may nest {MAX_SECTION_DEPTH} levels deep, no further",
            code="hospitality.menu_section_too_deep",
            details={"parent_id": str(parent_id), "max_depth": MAX_SECTION_DEPTH},
        )


async def create_section(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name: str,
    parent_id: uuid.UUID | None,
    sort_order: int,
) -> MenuSection:
    """Add a heading to the menu."""
    await _require_placeable(session, tenant_id, parent_id, moving=None)
    section = MenuSection(
        tenant_id=tenant_id, name=name.strip(), parent_id=parent_id, sort_order=sort_order
    )
    session.add(section)
    await session.flush()
    return section


async def update_section(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    section_id: uuid.UUID,
    *,
    name: str | None = None,
    parent_id: uuid.UUID | None = None,
    reparent: bool = False,
    sort_order: int | None = None,
) -> MenuSection:
    """Rename, reorder, or move a section.

    ``reparent`` distinguishes "leave the parent alone" from "make this a root section", which a
    nullable ``parent_id`` alone cannot say — the same PATCH-semantics problem every optional
    nullable field has, solved with an explicit flag rather than a sentinel.
    """
    section = await get_section(session, tenant_id, section_id)
    if reparent:
        await _require_placeable(session, tenant_id, parent_id, moving=section_id)
        section.parent_id = parent_id
    if name is not None:
        section.name = name.strip()
    if sort_order is not None:
        section.sort_order = sort_order
    await session.flush()
    return section


async def delete_section(
    session: AsyncSession, tenant_id: uuid.UUID, section_id: uuid.UUID
) -> None:
    """Remove a heading — refused while anything still hangs off it.

    Refusing rather than cascading is the deliberate half. A cascade here would silently unplace
    every dish under a mis-clicked delete, and the rows it removed carry no way back; a property
    that means it can empty the section first, which takes one drag per dish and cannot be done by
    accident.
    """
    section = await get_section(session, tenant_id, section_id)
    children = (
        await session.execute(
            select(func.count())
            .select_from(MenuSection)
            .where(MenuSection.tenant_id == tenant_id, MenuSection.parent_id == section_id)
        )
    ).scalar_one()
    dishes = (
        await session.execute(
            select(func.count())
            .select_from(MenuPlacement)
            .where(MenuPlacement.tenant_id == tenant_id, MenuPlacement.section_id == section_id)
        )
    ).scalar_one()
    if children or dishes:
        raise ConflictError(
            message="Empty the section before deleting it",
            code="hospitality.menu_section_not_empty",
            details={
                "section_id": str(section_id),
                "child_sections": int(children),
                "dishes": int(dishes),
            },
        )
    await session.delete(section)
    await session.flush()


def _clean_tags(tags: list[str]) -> list[str]:
    """Trim, lower-case and de-duplicate, preserving the order the caller sent."""
    seen: dict[str, None] = {}
    for raw in tags:
        tag = raw.strip().lower()
        if tag:
            seen.setdefault(tag, None)
    cleaned = list(seen)
    if len(cleaned) > MAX_TAGS_PER_ITEM:
        raise ValidationFailedError(
            message=f"A dish may carry at most {MAX_TAGS_PER_ITEM} tags",
            code="hospitality.menu_too_many_tags",
            details={"count": len(cleaned), "max": MAX_TAGS_PER_ITEM},
        )
    return cleaned


async def set_placement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    *,
    section_id: uuid.UUID | None,
    tags: list[str],
) -> tuple[uuid.UUID | None, list[str]]:
    """Put a dish on the menu: its one section and its whole tag set, REPLACED together.

    One call rather than four, because the two axes are edited on one screen and a half-applied
    edit ("moved but the tags did not take") is the failure a server would have to unpick by hand.
    ``section_id=None`` unplaces the dish; an empty tag list clears its tags.

    The item is validated to exist first (D-029: an opaque id with no FK means this check IS the
    referential integrity), so a typo cannot leave a placement pointing at nothing.
    """
    known = await inventory_queries.existing_item_ids(session, tenant_id, [item_id])
    if item_id not in known:
        raise ValidationFailedError(
            message="Referenced inventory item does not exist",
            code="hospitality.item_not_found",
            details={"item_ids": [str(item_id)]},
        )
    cleaned = _clean_tags(tags)
    if section_id is not None:
        await get_section(session, tenant_id, section_id)

    placement = (
        await session.execute(
            select(MenuPlacement).where(
                MenuPlacement.tenant_id == tenant_id, MenuPlacement.item_id == item_id
            )
        )
    ).scalar_one_or_none()
    if section_id is None:
        if placement is not None:
            await session.delete(placement)
    elif placement is None:
        session.add(MenuPlacement(tenant_id=tenant_id, item_id=item_id, section_id=section_id))
    else:
        placement.section_id = section_id

    # Replace the tag set: delete what is gone, insert what is new, leave what is unchanged
    # untouched so an edit that only moves the dish writes no tag rows at all.
    current = set(
        (
            await session.execute(
                select(MenuItemTag.tag).where(
                    MenuItemTag.tenant_id == tenant_id, MenuItemTag.item_id == item_id
                )
            )
        )
        .scalars()
        .all()
    )
    wanted = set(cleaned)
    if current - wanted:
        await session.execute(
            delete(MenuItemTag).where(
                MenuItemTag.tenant_id == tenant_id,
                MenuItemTag.item_id == item_id,
                MenuItemTag.tag.in_(sorted(current - wanted)),
            )
        )
    for tag in cleaned:
        if tag not in current:
            session.add(MenuItemTag(tenant_id=tenant_id, item_id=item_id, tag=tag))
    await session.flush()
    return section_id, cleaned


__all__ = [
    "MAX_TAGS_PER_ITEM",
    "create_section",
    "delete_section",
    "get_section",
    "set_placement",
    "update_section",
]
