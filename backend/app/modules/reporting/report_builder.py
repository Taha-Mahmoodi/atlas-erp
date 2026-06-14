"""The ad-hoc report builder (PLAN 13.2, D-059): validate a ReportSpec against the whitelist, build
the ORM select with TYPED BINDS, run it tenant-filtered, return JSON-safe rows (or stream CSV).

THE NO-INJECTION CONSTRUCTION (D-059, CRITICAL). The builder NEVER string-concatenates SQL. It maps
the spec's entity/column NAMES to the registry's pre-resolved ORM attributes (a closed allow-list —
unknown names are rejected, not reflected), builds a SQLAlchemy ``select()`` over those attributes,
and applies filters as TYPED, BOUND comparisons (the value is coerced to the column's Python type
like ``core/pagination`` does, then bound — a malicious-looking value such as ``"'; DROP TABLE"`` is
just a string compared for equality, matching nothing, executing nothing). Operators come from the
fixed ``FilterOperator`` set; aggregations from the fixed ``Aggregation`` set.

TENANCY IS AUTO-APPLIED (D-007). The select runs through the tenant-filtered session, so
``core/tenancy.do_orm_execute`` injects the ``tenant_id == current`` predicate into every ORM
statement — the builder writes no tenant WHERE itself; tenant A can never see tenant B's rows (a
test pins this). Every whitelisted model is a ``TenantMixin``, so the listener always fires.

THE 10K CAP + TRUNCATION (PERFORMANCE §3). The JSON path fetches CAP + 1 rows; if the extra row
arrives the result is truncated to CAP and ``truncated=True`` (the UI then offers the streaming CSV
export). A spec ``limit`` can only LOWER the cap, never raise it. ORDER BY a stable key (the
entity's ``default_order_column`` + the PK) so paging/streaming and tests are deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import AtlasError
from app.modules.reporting.constants import REPORT_ROW_CAP, Aggregation, FilterOperator
from app.modules.reporting.report_registry import (
    ReportableEntity,
    ReportColumn,
    get_entity,
)
from app.modules.reporting.schemas import (
    ReportAggregation,
    ReportFilter,
    ReportResult,
    ReportSpec,
)

_INVALID = "reporting.invalid_report"
# Streaming pulls rows in batches so the export never materializes the whole result set (the
# stream_results execution option yields server-side; this is the per-yield buffer size).
_STREAM_BATCH = 1_000


def _bad(message: str) -> AtlasError:
    """A 400 with the report-builder envelope code (D-014/D-059). A malformed report (unknown
    entity/column/operator, a non-filterable/groupable column used as such, a bad value) is a
    client error — 400 ``reporting.invalid_report``, distinct from a generic 422 validation fail."""
    return AtlasError(code=_INVALID, message=message, status_code=400)


# --- Spec validation against the whitelist (D-059) ----------------------------


def _resolve_entity(spec: ReportSpec) -> ReportableEntity:
    entity = get_entity(spec.entity)
    if entity is None:
        raise _bad(f"Unknown report entity: {spec.entity}")
    return entity


def _resolve_column(entity: ReportableEntity, name: str) -> ReportColumn:
    column = entity.columns.get(name)
    if column is None:
        raise _bad(f"Unknown column '{name}' for entity '{entity.key}'")
    return column


def _coerce_scalar(column: ReportColumn, value: Any) -> Any:
    """Coerce a filter value to the column's Python type so the bound comparison is well-typed on
    both engines (the ``core/pagination._coerce_key_value`` discipline). The value stays DATA — it
    is bound, never interpolated (D-059). A value that cannot coerce is a 400, not a 500."""
    if value is None:
        return None
    try:
        if column.type == "number":
            return value if isinstance(value, Decimal) else Decimal(str(value))
        if column.type == "date":
            return value if isinstance(value, date) else date.fromisoformat(str(value))
        if column.type == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"true", "1", "yes"}
        return str(value)
    except (InvalidOperation, ValueError) as exc:
        raise _bad(f"Value '{value}' is not a valid {column.type} for filter") from exc


def _filter_clause(column: ReportColumn, flt: ReportFilter) -> sa.ColumnElement[bool]:
    """Build ONE typed, bound filter predicate (D-059). Every branch compares the ORM attribute to a
    COERCED, BOUND value — no branch ever interpolates the value into SQL text."""
    attr = column.attr
    # ApiModel uses ``use_enum_values=True`` so ``flt.operator`` arrives as the StrEnum's str value;
    # normalize back to the enum member so the identity comparisons below are exact.
    op = FilterOperator(flt.operator)
    if op is FilterOperator.IS_NULL:
        want_null = bool(flt.value) if flt.value is not None else True
        return attr.is_(None) if want_null else attr.isnot(None)
    if op is FilterOperator.IN:
        if not isinstance(flt.value, list) or not flt.value:
            raise _bad(f"Filter '{flt.column}' with IN needs a non-empty list value")
        return attr.in_([_coerce_scalar(column, item) for item in flt.value])
    if op is FilterOperator.BETWEEN:
        if not isinstance(flt.value, list) or len(flt.value) != 2:
            raise _bad(f"Filter '{flt.column}' with BETWEEN needs a [low, high] value")
        low, high = (_coerce_scalar(column, part) for part in flt.value)
        return attr.between(low, high)
    if op is FilterOperator.LIKE:
        if column.type != "str":
            raise _bad(f"Filter '{flt.column}' with LIKE requires a string column")
        # ilike on a bound pattern — the value is escaped/bound, never concatenated into SQL.
        return attr.ilike(f"%{_coerce_scalar(column, flt.value)}%")
    value = _coerce_scalar(column, flt.value)
    comparisons = {
        FilterOperator.EQ: attr == value,
        FilterOperator.NE: attr != value,
        FilterOperator.GT: attr > value,
        FilterOperator.GTE: attr >= value,
        FilterOperator.LT: attr < value,
        FilterOperator.LTE: attr <= value,
    }
    return comparisons[op]


def _aggregate_expr(
    entity: ReportableEntity, agg: ReportAggregation
) -> tuple[str, sa.ColumnElement[Any]]:
    """Build ONE aggregate expression + its result alias (D-059). COUNT may omit a column
    (COUNT(*)) or count any whitelisted column; SUM/AVG/MIN/MAX need an aggregatable column."""
    # ApiModel uses ``use_enum_values=True`` so ``agg.func`` arrives as the StrEnum's str value;
    # normalize back to the enum member for exact comparison + a clean alias.
    func = Aggregation(agg.func)
    if func is Aggregation.COUNT:
        if agg.column is None:
            alias = agg.alias or "count"
            return alias, sa.func.count().label(alias)
        column = _resolve_column(entity, agg.column)
        alias = agg.alias or f"count_{agg.column}"
        return alias, sa.func.count(column.attr).label(alias)
    if agg.column is None:
        raise _bad(f"Aggregation {func.value} requires a column")
    column = _resolve_column(entity, agg.column)
    if not column.is_aggregatable:
        raise _bad(f"Column '{agg.column}' is not aggregatable")
    funcs = {
        Aggregation.SUM: sa.func.sum,
        Aggregation.AVG: sa.func.avg,
        Aggregation.MIN: sa.func.min,
        Aggregation.MAX: sa.func.max,
    }
    alias = agg.alias or f"{func.value}_{agg.column}"
    return alias, funcs[func](column.attr).label(alias)


def _selected(spec: ReportSpec, entity: ReportableEntity) -> tuple[list[str], list[Any]]:
    """The ordered (result-column-name, selectable) pairs for the spec (D-059).

    Grouped: the group-by columns (each whitelisted + ``groupable``) followed by the aggregates.
    Flat: the requested ``columns`` (each whitelisted + non-empty)."""
    names: list[str] = []
    selectables: list[Any] = []
    if spec.group_by:
        for name in spec.group_by:
            column = _resolve_column(entity, name)
            if not column.groupable:
                raise _bad(f"Column '{name}' is not groupable")
            names.append(name)
            selectables.append(column.attr.label(name))
        if not spec.aggregations:
            raise _bad("A grouped report requires at least one aggregation")
        for agg in spec.aggregations:
            alias, expr = _aggregate_expr(entity, agg)
            names.append(alias)
            selectables.append(expr)
        return names, selectables
    if spec.aggregations:
        raise _bad("Aggregations require a group_by")
    requested = spec.columns or list(entity.columns)
    for name in requested:
        column = _resolve_column(entity, name)
        names.append(name)
        selectables.append(column.attr.label(name))
    return names, selectables


def _order_columns(entity: ReportableEntity, spec: ReportSpec) -> list[InstrumentedAttribute[Any]]:
    """A STABLE ORDER BY (D-059). Grouped: by the group-by columns. Flat: by the entity's
    default_order_column (when whitelisted) then the PK, so streaming/paging is deterministic."""
    if spec.group_by:
        return [entity.columns[name].attr for name in spec.group_by]
    order: list[InstrumentedAttribute[Any]] = []
    default = entity.default_order_column
    if default and default in entity.columns:
        order.append(entity.columns[default].attr)
    order.append(entity.model.id)
    return order


def _build_select(spec: ReportSpec, entity: ReportableEntity) -> tuple[list[str], sa.Select[Any]]:
    """Validate the spec + assemble the ORM select (no execution). Returns (result column names,
    statement). Tenancy is NOT added here — ``do_orm_execute`` injects it at execution (D-007)."""
    names, selectables = _selected(spec, entity)
    stmt = sa.select(*selectables)
    for flt in spec.filters:
        column = _resolve_column(entity, flt.column)
        if not column.filterable:
            raise _bad(f"Column '{flt.column}' is not filterable")
        stmt = stmt.where(_filter_clause(column, flt))
    if spec.group_by:
        stmt = stmt.group_by(*(entity.columns[name].attr for name in spec.group_by))
    stmt = stmt.order_by(*_order_columns(entity, spec))
    return names, stmt


def _effective_cap(spec: ReportSpec) -> int:
    """The row cap for this run: the 10k cap, lowered (never raised) by a positive spec.limit."""
    if spec.limit is not None and 0 < spec.limit < REPORT_ROW_CAP:
        return spec.limit
    return REPORT_ROW_CAP


def _json_value(value: Any) -> Any:
    """JSON-safe encode one cell (D-015/D-059): Decimal → exact string, date/datetime → ISO, UUID →
    str, everything else as-is (bool/int/float/str/None pass)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _row_dict(names: list[str], row: Row[Any]) -> dict[str, Any]:
    return {name: _json_value(value) for name, value in zip(names, row, strict=True)}


# --- The run entry points (D-059) ---------------------------------------------


def validate_spec(spec: ReportSpec) -> None:
    """Validate ``spec`` against the whitelist WITHOUT executing (D-059). Raises the 400
    ``reporting.invalid_report`` envelope on any unknown/disallowed entity/column/operator. The
    streaming CSV path calls this first so a malformed report fails BEFORE the 200 stream begins
    (a mid-stream error after headers are sent is unrecoverable for the client)."""
    entity = _resolve_entity(spec)
    _build_select(spec, entity)


async def run_report(session: AsyncSession, spec: ReportSpec) -> ReportResult:
    """Run an ad-hoc report and return the JSON grid (D-059). Validates ``spec`` against the
    whitelist (400 ``reporting.invalid_report`` on any unknown/disallowed entity/column/operator),
    builds the ORM select with typed binds, runs it through the TENANT-FILTERED session (D-007 auto-
    scopes it), CAPS at 10k rows + 1 to flag truncation (PERFORMANCE §3), and returns JSON-safe
    rows. The caller must already hold the entity's source permission (the router enforces that)."""
    entity = _resolve_entity(spec)
    names, stmt = _build_select(spec, entity)
    cap = _effective_cap(spec)
    result = await session.execute(stmt.limit(cap + 1))
    fetched = result.all()
    truncated = len(fetched) > cap
    rows = [_row_dict(names, row) for row in fetched[:cap]]
    return ReportResult(
        columns=names, rows=rows, row_count=len(rows), truncated=truncated
    )


async def stream_report_csv(session: AsyncSession, spec: ReportSpec) -> AsyncIterator[str]:
    """Stream the report as CSV rows, generated LAZILY (PERFORMANCE §3): the header line, then one
    data line per row, pulled from the DB in batches via ``stream_results`` so the full set is never
    materialized in memory. The CSV export is NOT capped at 10k — it is the path for results larger
    than the JSON grid. Each yielded chunk is a complete CSV line (CRLF-terminated, RFC 4180)."""
    import csv  # local import: only the export path needs the csv module
    import io

    entity = _resolve_entity(spec)
    names, stmt = _build_select(spec, entity)

    def _line(values: list[Any]) -> str:
        buffer = io.StringIO()
        csv.writer(buffer).writerow(values)
        return buffer.getvalue()

    yield _line(names)
    stream = await session.stream(stmt.execution_options(stream_results=True))
    async for partition in stream.partitions(_STREAM_BATCH):
        for row in partition:
            yield _line([_json_value(value) for value in row])
