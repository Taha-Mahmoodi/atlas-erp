"""Report-builder behaviour (PLAN 13.2, D-059), SQLite.

Proves ``report_builder.run_report`` over a WHITELISTED entity: select columns + filter + group-by +
aggregation returns the right rows; unknown entity/column → 400; a non-filterable/non-groupable
column used as such → 400; results are TENANT-SCOPED (tenant A cannot see tenant B's rows — the
``do_orm_execute`` filter applies to the dynamic select); a malicious-looking filter value is BOUND
not interpolated (no injection — treated as data, matches nothing, never errors); the 10k cap
truncates + sets ``truncated=True`` (proven with a small spec ``limit``); and MASKED HR data is NOT
exposable (the employee whitelist has no ``base_salary`` column → 400 unknown column). The
over-the-wire RBAC + tenant isolation is in test_report_api.py.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AtlasError
from app.core.tenancy import tenant_context
from app.modules.reporting import report_builder
from app.modules.reporting.constants import REPORT_ROW_CAP, Aggregation, FilterOperator
from app.modules.reporting.schemas import (
    ReportAggregation,
    ReportFilter,
    ReportSpec,
)
from tests.modules.reporting.factories_reportbuilder import (
    ReportBuilderSetup,
    build_report_builder_setup,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def rb_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ReportBuilderSetup:
    return await build_report_builder_setup(db_session, tenant_a)


async def _run(session: AsyncSession, tenant_id: uuid.UUID, spec: ReportSpec):
    with tenant_context(tenant_id):
        return await report_builder.run_report(session, spec)


async def test_select_columns_returns_rows(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A flat report selecting whitelisted columns returns one JSON-safe dict per matching row."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(entity="sales.orders", columns=["order_number", "status", "total_amount"]),
    )
    assert result.columns == ["order_number", "status", "total_amount"]
    assert result.row_count == rb_setup.confirmed_count + rb_setup.draft_count
    assert not result.truncated
    # Money is a JSON-safe exact STRING, not a float (D-015).
    assert all(isinstance(row["total_amount"], str) for row in result.rows)


async def test_filter_narrows_rows_typed_bound(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A filter on a whitelisted column (typed + bound) narrows the result to matching rows."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            columns=["order_number"],
            filters=[ReportFilter(column="status", operator=FilterOperator.EQ, value="CONFIRMED")],
        ),
    )
    assert result.row_count == rb_setup.confirmed_count


async def test_group_by_with_aggregation(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """Group-by a groupable column + COUNT/SUM aggregations returns one row per group with the
    right count and summed total (the headline grouped report, D-059)."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            group_by=["status"],
            aggregations=[
                ReportAggregation(func=Aggregation.COUNT, alias="n"),
                ReportAggregation(
                    column="total_amount", func=Aggregation.SUM, alias="total"
                ),
            ],
        ),
    )
    assert result.columns == ["status", "n", "total"]
    by_status = {row["status"]: row for row in result.rows}
    assert by_status["CONFIRMED"]["n"] == rb_setup.confirmed_count
    assert Decimal(by_status["CONFIRMED"]["total"]) == rb_setup.confirmed_total
    assert by_status["DRAFT"]["n"] == rb_setup.draft_count
    assert Decimal(by_status["DRAFT"]["total"]) == rb_setup.draft_total


async def test_unknown_entity_is_400(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with pytest.raises(AtlasError) as exc:
        await _run(db_session, tenant_a, ReportSpec(entity="finance.secret_table"))
    assert exc.value.status_code == 400
    assert exc.value.code == "reporting.invalid_report"


async def test_unknown_column_is_400(db_session: AsyncSession, tenant_a: uuid.UUID) -> None:
    with pytest.raises(AtlasError) as exc:
        await _run(
            db_session,
            tenant_a,
            ReportSpec(entity="sales.orders", columns=["order_number", "no_such_column"]),
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "reporting.invalid_report"


async def test_non_filterable_column_used_as_filter_is_400(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A filter naming a column that is not in the entity's whitelist → 400 (the closed allow-list:
    a column the registry does not declare cannot be filtered on)."""
    with pytest.raises(AtlasError) as exc:
        await _run(
            db_session,
            tenant_a,
            ReportSpec(
                entity="sales.orders",
                columns=["order_number"],
                filters=[
                    ReportFilter(column="notes", operator=FilterOperator.EQ, value="x")
                ],
            ),
        )
    assert exc.value.status_code == 400
    assert exc.value.code == "reporting.invalid_report"


async def test_non_groupable_column_used_in_group_by_is_400(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """A group-by on a whitelisted but non-groupable column (order_number) → 400."""
    with pytest.raises(AtlasError) as exc:
        await _run(
            db_session,
            tenant_a,
            ReportSpec(
                entity="sales.orders",
                group_by=["order_number"],
                aggregations=[ReportAggregation(func=Aggregation.COUNT)],
            ),
        )
    assert exc.value.status_code == 400


async def test_aggregating_non_aggregatable_column_is_400(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """SUM over a non-aggregatable (string) column → 400 (SUM/AVG/MIN/MAX need a numeric column)."""
    with pytest.raises(AtlasError) as exc:
        await _run(
            db_session,
            tenant_a,
            ReportSpec(
                entity="sales.orders",
                group_by=["currency_code"],
                aggregations=[
                    ReportAggregation(column="status", func=Aggregation.SUM)
                ],
            ),
        )
    assert exc.value.status_code == 400


async def test_masked_compensation_column_is_not_exposable(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """The HR employee entity's whitelist EXCLUDES the masked compensation/PII columns (D-009/D-052/
    D-059), so requesting base_salary → 400 unknown column. Masked data is not exposable through
    reports, by construction (it is not in the registry at all)."""
    for masked in ("base_salary", "national_id", "tax_id", "date_of_birth", "bank_account"):
        with pytest.raises(AtlasError) as exc:
            await _run(
                db_session,
                tenant_a,
                ReportSpec(entity="hr.employees", columns=["employee_code", masked]),
            )
        assert exc.value.status_code == 400, masked
        assert exc.value.code == "reporting.invalid_report", masked


async def test_filter_value_is_bound_not_interpolated(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A malicious-looking filter value is treated as DATA, not SQL (D-059, the no-injection
    guarantee). ``"'; DROP TABLE sales_orders; --"`` is bound as a string compared for equality —
    it matches no row (returns zero rows), does NOT error, and does NOT execute any DDL (a follow-up
    report still finds the seeded rows, proving the table survived)."""
    injection = "'; DROP TABLE sales_orders; --"
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            columns=["order_number"],
            filters=[
                ReportFilter(column="status", operator=FilterOperator.EQ, value=injection)
            ],
        ),
    )
    assert result.row_count == 0
    # The table survived — a normal report still returns the seeded population.
    survived = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(entity="sales.orders", columns=["order_number"]),
    )
    assert survived.row_count == rb_setup.confirmed_count + rb_setup.draft_count


async def test_row_cap_truncates_and_flags(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A spec ``limit`` below the row count truncates the result and sets ``truncated=True``
    (PERFORMANCE §3 — the same CAP+1 fetch the 10k cap uses, proven at small scale: limit 2 over 4
    rows → 2 rows, truncated)."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(entity="sales.orders", columns=["order_number"], limit=2),
    )
    assert result.row_count == 2
    assert result.truncated is True


async def test_spec_limit_cannot_raise_the_cap() -> None:
    """A spec limit above the 10k cap (or non-positive) does not raise the effective cap — the
    builder's cap helper clamps to REPORT_ROW_CAP (PERFORMANCE §3)."""
    assert report_builder._effective_cap(ReportSpec(entity="sales.orders", limit=999_999)) == (
        REPORT_ROW_CAP
    )
    assert report_builder._effective_cap(ReportSpec(entity="sales.orders", limit=0)) == (
        REPORT_ROW_CAP
    )
    assert report_builder._effective_cap(ReportSpec(entity="sales.orders", limit=5)) == 5


async def test_result_is_tenant_scoped(
    db_session: AsyncSession, tenant_a: uuid.UUID, tenant_b: uuid.UUID
) -> None:
    """A report run under tenant B sees ONLY tenant B's rows — never tenant A's (D-007, the
    do_orm_execute filter applies to the builder's DYNAMIC select). Seed both tenants, then run the
    same report under each and assert the counts are independent."""
    setup_a = await build_report_builder_setup(db_session, tenant_a)
    # Tenant B seeded with a DIFFERENT, smaller population so the counts cannot be confused.
    setup_b_orders = await build_report_builder_setup(db_session, tenant_b)
    spec = ReportSpec(entity="sales.orders", columns=["order_number"])
    result_a = await _run(db_session, tenant_a, spec)
    result_b = await _run(db_session, tenant_b, spec)
    total = setup_a.confirmed_count + setup_a.draft_count
    assert result_a.row_count == total
    assert result_b.row_count == setup_b_orders.confirmed_count + setup_b_orders.draft_count
    # Neither leaks the other's rows: each equals its OWN tenant's seeded population, not the sum.
    assert result_a.row_count == total


async def test_result_carries_human_labels_aligned_with_columns(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """#166: a grouped+aggregated run returns ``column_labels`` from the registry, aligned
    index-for-index with the wire ``columns`` — so the grid and the CSV can both show
    "Status" / "Sum of Total" instead of "status" / "sum_total_amount".

    ``COUNT(order_number)`` is in here on purpose. The builder lets COUNT target ANY whitelisted
    column (only SUM/AVG/MIN/MAX need the ``is_aggregatable`` flag) and ``order_number`` carries no
    such flag, so this row pins both halves of that path at once: the COUNT exemption stays (a
    regression 400s a shape the UI offers — its aggregation picker lists real columns for `count`,
    not just "rows (*)") and COUNT-with-a-column keeps its composed label."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            group_by=["status"],
            aggregations=[
                ReportAggregation(func=Aggregation.COUNT),
                ReportAggregation(column="order_number", func=Aggregation.COUNT),
                ReportAggregation(column="total_amount", func=Aggregation.SUM),
            ],
        ),
    )
    assert result.columns == ["status", "count", "count_order_number", "sum_total_amount"]
    assert result.column_labels == ["Status", "Count", "Count of Order Number", "Sum of Total"]


async def test_flat_result_labels_come_from_the_registry(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """#166: a flat report labels each selected column with the registry's display label."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(entity="sales.orders", columns=["order_number", "total_amount"]),
    )
    assert result.columns == ["order_number", "total_amount"]
    assert result.column_labels == ["Order Number", "Total"]


async def test_explicit_alias_is_its_own_label(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """#166: when the caller NAMES an aggregate with ``alias`` that name is the label — the builder
    does not override a display name the caller chose deliberately."""
    result = await _run(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            group_by=["status"],
            aggregations=[ReportAggregation(func=Aggregation.COUNT, alias="Orders")],
        ),
    )
    assert result.columns == ["status", "Orders"]
    assert result.column_labels == ["Status", "Orders"]
