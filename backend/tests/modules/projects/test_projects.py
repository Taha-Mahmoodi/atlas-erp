"""Project CRUD + customer / cost-centre validation at the SERVICE layer (PLAN 11.1, D-056).

The service owns every rule (CLAUDE.md rule 7): a unique code per tenant, a customer that exists in
sales when set, a cost centre that exists in finance when set. Service-level tests run under the
tenant context (D-025); the API surface is exercised separately in test_projects_api.py.
"""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.core.tenancy import tenant_context
from app.modules.projects import service
from app.modules.projects.constants import ProjectStatus
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate
from tests.modules.projects.factories import ProjectsSetup, build_project

pytestmark = pytest.mark.asyncio


async def test_create_project_sets_fields(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id):
        project = await service.create_project(
            db_session,
            projects_setup.tenant_id,
            ProjectCreate(
                code="PRJ-NEW",
                name="New build",
                customer_id=projects_setup.customer_id,
                cost_center_id=projects_setup.cost_center_id,
                status=ProjectStatus.ACTIVE,
            ),
        )
        await db_session.commit()
    assert project.code == "PRJ-NEW"
    assert project.status == ProjectStatus.ACTIVE.value
    assert project.customer_id == projects_setup.customer_id
    assert project.cost_center_id == projects_setup.cost_center_id
    assert project.is_active is True


async def test_create_duplicate_code_conflicts(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(ConflictError) as exc:
        await service.create_project(
            db_session,
            projects_setup.tenant_id,
            ProjectCreate(code=projects_setup.project_code, name="Dup"),
        )
    assert exc.value.code == "projects.project_code_conflict"


async def test_create_with_unknown_customer_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_project(
            db_session,
            projects_setup.tenant_id,
            ProjectCreate(code="PRJ-X", name="X", customer_id=uuid.uuid4()),
        )
    assert exc.value.code == "projects.customer_not_found"


async def test_create_with_unknown_cost_center_rejected(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.create_project(
            db_session,
            projects_setup.tenant_id,
            ProjectCreate(code="PRJ-Y", name="Y", cost_center_id=uuid.uuid4()),
        )
    assert exc.value.code == "projects.cost_center_not_found"


async def test_update_project_revalidates_customer(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(ValidationFailedError) as exc:
        await service.update_project(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            ProjectUpdate(customer_id=uuid.uuid4()),
        )
    assert exc.value.code == "projects.customer_not_found"


async def test_update_project_mutates_loaded_object(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id):
        updated = await service.update_project(
            db_session,
            projects_setup.tenant_id,
            projects_setup.project_id,
            ProjectUpdate(name="Renamed", status=ProjectStatus.CLOSED),
        )
        await db_session.commit()
    assert updated.name == "Renamed"
    assert updated.status == ProjectStatus.CLOSED.value


async def test_get_missing_project_404(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    with tenant_context(projects_setup.tenant_id), pytest.raises(NotFoundError) as exc:
        await service.get_project(db_session, projects_setup.tenant_id, uuid.uuid4())
    assert exc.value.code == "projects.project_not_found"


async def test_list_projects_filtered_by_status(
    db_session: AsyncSession, projects_setup: ProjectsSetup
) -> None:
    await build_project(
        db_session,
        projects_setup.tenant_id,
        code="PRJ-ACTIVE",
        status=ProjectStatus.ACTIVE,
    )
    from app.modules.projects.schemas import ProjectFilter

    with tenant_context(projects_setup.tenant_id):
        page = await service.list_projects(
            db_session,
            projects_setup.tenant_id,
            filters=ProjectFilter(status=ProjectStatus.ACTIVE),
        )
    codes = {p.code for p in page.items}
    assert "PRJ-ACTIVE" in codes
    # The setup project is PLANNING (the default), so the ACTIVE filter excludes it.
    assert projects_setup.project_code not in codes
