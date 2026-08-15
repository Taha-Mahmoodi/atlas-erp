"""Report-builder CSV export (PLAN 13.2, D-059, PERFORMANCE §3), SQLite.

Proves ``report_builder.stream_report_csv`` yields the header line then the right data rows, lazily
(streamed, never materialized), with money as exact strings; and that a malformed spec is rejected
by ``validate_spec`` BEFORE the stream begins. The over-the-wire content-type / disposition is in
test_report_api.py.
"""

import csv
import io
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AtlasError
from app.core.tenancy import tenant_context
from app.modules.reporting import report_builder
from app.modules.reporting.schemas import ReportSpec
from tests.modules.reporting.factories_reportbuilder import (
    ReportBuilderSetup,
    build_report_builder_setup,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def rb_setup(db_session: AsyncSession, tenant_a: uuid.UUID) -> ReportBuilderSetup:
    return await build_report_builder_setup(db_session, tenant_a)


async def _collect_csv(
    session: AsyncSession, tenant_id: uuid.UUID, spec: ReportSpec
) -> list[list[str]]:
    """Drain the CSV stream into parsed rows (header + data) for assertions."""
    chunks: list[str] = []
    with tenant_context(tenant_id):
        async for chunk in report_builder.stream_report_csv(session, spec):
            chunks.append(chunk)
    return list(csv.reader(io.StringIO("".join(chunks))))


async def test_csv_has_header_and_data_rows(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """The stream is the header line then one data line per row, money as exact strings. The header
    carries the registry's DISPLAY labels, not the wire column names (#166)."""
    rows = await _collect_csv(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(entity="sales.orders", columns=["order_number", "status", "total_amount"]),
    )
    assert rows[0] == ["Order Number", "Status", "Total"]
    data = rows[1:]
    assert len(data) == rb_setup.confirmed_count + rb_setup.draft_count
    # Money column is a plain decimal string in the CSV cell.
    for row in data:
        assert "." in row[2]  # e.g. "50.000000"


async def test_csv_export_reflects_filter(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A filtered export streams only the matching rows (the same select the JSON path builds)."""
    from app.modules.reporting.constants import FilterOperator
    from app.modules.reporting.schemas import ReportFilter

    rows = await _collect_csv(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            columns=["order_number"],
            filters=[ReportFilter(column="status", operator=FilterOperator.EQ, value="DRAFT")],
        ),
    )
    assert len(rows) - 1 == rb_setup.draft_count  # minus the header line


async def test_csv_export_grouped(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """A grouped export streams the group-by + aggregate columns (one line per group). The group-by
    column shows its registry label; a caller-chosen ``alias`` stays as given (#166)."""
    from app.modules.reporting.constants import Aggregation
    from app.modules.reporting.schemas import ReportAggregation

    rows = await _collect_csv(
        db_session,
        rb_setup.tenant_id,
        ReportSpec(
            entity="sales.orders",
            group_by=["status"],
            aggregations=[ReportAggregation(func=Aggregation.COUNT, alias="n")],
        ),
    )
    assert rows[0] == ["Status", "n"]
    by_status = {row[0]: row[1] for row in rows[1:]}
    assert by_status["CONFIRMED"] == str(rb_setup.confirmed_count)
    assert by_status["DRAFT"] == str(rb_setup.draft_count)


async def test_csv_header_matches_the_json_grid_labels(
    db_session: AsyncSession, rb_setup: ReportBuilderSetup
) -> None:
    """#166: the CSV header line IS ``ReportResult.column_labels`` — grid and export take their
    headers from the SAME source, so they cannot drift apart again."""
    spec = ReportSpec(entity="sales.orders", columns=["order_number", "order_date"])
    rows = await _collect_csv(db_session, rb_setup.tenant_id, spec)
    with tenant_context(rb_setup.tenant_id):
        result = await report_builder.run_report(db_session, spec)
    assert rows[0] == result.column_labels
    assert rows[0] != result.columns  # the wire names are NOT what either surface shows


async def test_export_validates_spec_before_streaming(
    db_session: AsyncSession, tenant_a: uuid.UUID
) -> None:
    """``validate_spec`` rejects a malformed spec with the 400 envelope BEFORE the stream begins, so
    the export endpoint never sends a 200 then errors mid-body (D-059)."""
    with pytest.raises(AtlasError) as exc:
        report_builder.validate_spec(ReportSpec(entity="finance.secret_table"))
    assert exc.value.status_code == 400
    assert exc.value.code == "reporting.invalid_report"
