"""WBS-element CRUD + the tree + cycle guard + code-unique-within-project (PLAN 11.1, D-056).

A WBS element belongs to a project and forms a tree via ``parent_id``. The service owns every rule
(CLAUDE.md rule 7): the project must exist; the code is unique WITHIN the project (the same code may
recur under a DIFFERENT project); a parent (when set) must belong to the same project, exist, and
not create a cycle. The WBS element id is the costing object a posting tags (D-056).
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.projects import service
from app.modules.projects.constants import WbsStatus
from app.modules.projects.schemas import WbsElementCreate, WbsElementUpdate
from tests.modules.projects.factories import (
    ProjectsSetup,
    build_project,
    build_wbs_element,
)

pytestmark = pytest.mark.asyncio


async def test_create_wbs_under_project(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    element = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-A",
        budget_amount=Decimal("500"),
    )
    assert element.project_id == projects_setup.project_id
    assert element.status == WbsStatus.OPEN.value
    assert element.parent_id is None
    assert Decimal(str(element.budget_amount)) == Decimal("500")


async def test_create_wbs_under_missing_project_404(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.create_wbs_element(
            db_session,
            projects_setup.tenant_id,
            uuid.uuid4(),
            WbsElementCreate(code="WBS-Z", name="Orphan"),
        )
    assert exc.value.code == "projects.project_not_found"


async def test_wbs_code_unique_within_project(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-DUP"
    )
    with tenant_context(projects_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_wbs_element(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            WbsElementCreate(code="WBS-DUP", name="Dup"),
        )
    assert exc.value.code == "projects.wbs_code_conflict"


async def test_same_wbs_code_allowed_in_different_project(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """The WBS code is unique only WITHIN a project (D-056): the same code may recur elsewhere."""
    await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-SHARED"
    )
    other = await build_project(db_session, projects_setup.tenant_id, code="PRJ-OTHER")
    element = await build_wbs_element(
        db_session, projects_setup.tenant_id, other.id, code="WBS-SHARED"
    )
    assert element.code == "WBS-SHARED"
    assert element.project_id == other.id


async def test_wbs_tree_parent_child(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    parent = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-P"
    )
    child = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-C",
        parent_id=parent.id,
    )
    assert child.parent_id == parent.id


async def test_wbs_self_parent_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    element = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-SELF"
    )
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.update_wbs_element(
            db_session,
            projects_setup.tenant_id,
            element.id,
            WbsElementUpdate(parent_id=element.id),
        )
    assert exc.value.code == "projects.wbs_cycle"


async def test_wbs_cycle_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    """A → B → A would close a loop; the guard rejects re-parenting A under its own descendant B."""
    a = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-CY-A"
    )
    b = await build_wbs_element(
        db_session,
        projects_setup.tenant_id,
        projects_setup.project_id,
        code="WBS-CY-B",
        parent_id=a.id,
    )
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.update_wbs_element(
            db_session,
            projects_setup.tenant_id,
            a.id,
            WbsElementUpdate(parent_id=b.id),
        )
    assert exc.value.code == "projects.wbs_cycle"


async def test_wbs_parent_from_other_project_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    other = await build_project(db_session, projects_setup.tenant_id, code="PRJ-XPARENT")
    foreign_parent = await build_wbs_element(
        db_session, projects_setup.tenant_id, other.id, code="WBS-FOREIGN"
    )
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_wbs_element(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            WbsElementCreate(code="WBS-BAD", name="Bad", parent_id=foreign_parent.id),
        )
    assert exc.value.code == "projects.wbs_parent_other_project"


async def test_wbs_unknown_parent_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_wbs_element(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            WbsElementCreate(code="WBS-NP", name="No parent", parent_id=uuid.uuid4()),
        )
    assert exc.value.code == "projects.wbs_not_found"


async def test_update_wbs_status_closed(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    element = await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-CL"
    )
    with tenant_context(projects_setup.tenant_id):
        updated = await service.update_wbs_element(
            db_session,
            projects_setup.tenant_id,
            element.id,
            WbsElementUpdate(status=WbsStatus.CLOSED),
        )
        await db_session.commit()
    assert updated.status == WbsStatus.CLOSED.value


async def test_list_wbs_elements_of_project(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-L1"
    )
    await build_wbs_element(
        db_session, projects_setup.tenant_id, projects_setup.project_id, code="WBS-L2"
    )
    from app.modules.projects.schemas import WbsElementFilter

    with tenant_context(projects_setup.tenant_id):
        page = await service.list_wbs_elements(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            filters=WbsElementFilter(),
        )
    codes = {e.code for e in page.items}
    assert {"WBS-L1", "WBS-L2"} <= codes
