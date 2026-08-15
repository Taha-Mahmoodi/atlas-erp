"""Reporting (dashboard) API schemas (PLAN 13.1, D-058): the typed KPI sub-models + the dashboard
envelope.

Each KPI is its own typed sub-model (a card's worth of data): ``MoneyKpi`` (a single money figure +
currency), ``AgingSummary`` (the four aging buckets + total), ``CountValueKpi`` (a count + a money
total — open orders), ``OtdKpi`` (an on-time-delivery percentage + its numerator/denominator). The
``DashboardResponse`` holds every KPI as an OPTIONAL field: the role-based endpoint returns ONLY the
KPIs the caller is permitted to see (a missing permission ⇒ that field is ``None`` and is omitted
from the JSON), so the response shape IS the role (D-058).

MONEY AS STRINGS (build-spec §13.1). Dashboard money fields serialize as STRINGS, not JSON numbers —
a KPI card is a display surface read by JS clients where a float round-trip would corrupt the exact
decimal. ``MoneyStr`` is a ``Decimal`` annotated with a ``PlainSerializer`` that renders the exact
decimal string (the value stays a ``Decimal`` in Python for arithmetic; only the wire form is a
string). ``percent`` is a plain number (it is a ratio, not money).
"""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import PlainSerializer

from app.core.schemas import ApiModel
from app.modules.reporting.constants import Aggregation, FilterOperator

# A money Decimal that serializes to its exact decimal STRING on the wire (build-spec §13.1). The
# value remains a Decimal in Python; only JSON rendering differs from the number-valued money in the
# transactional Read schemas.
MoneyStr = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str)]


class MoneyKpi(ApiModel):
    """A single-figure money KPI card (D-058): cash position, inventory value, WIP value. ``value``
    is the exact decimal as a string; ``currency`` is the tenant's functional currency code."""

    value: MoneyStr
    currency: str


class AgingSummary(ApiModel):
    """An AR/AP aging KPI card (D-058): the rolled-up bucket totals (current / 1-30 / 31-60 / 90+) +
    grand total — the dashboard collapses the aging report's 61-90 + over-90 tail into one 90+
    bucket. Money fields are exact-decimal strings. ``currency`` names the figures' currency."""

    current: MoneyStr
    d30: MoneyStr
    d60: MoneyStr
    d90plus: MoneyStr
    total: MoneyStr
    currency: str


class CountValueKpi(ApiModel):
    """An open-orders KPI card (D-058): a count of documents + their summed money value (open sales
    orders, open purchase orders). ``total`` is the exact-decimal string."""

    count: int
    total: MoneyStr
    currency: str


class OtdKpi(ApiModel):
    """The on-time-delivery KPI card (D-058): the percentage of measured deliveries that shipped on
    or before the order's requested date, plus its numerator/denominator. ``percent`` is a ratio (0-
    100), rounded to one decimal; ``total`` 0 ⇒ no measurable deliveries (percent presents as 0)."""

    percent: float
    on_time: int
    total: int


class FailedJobsKpi(ApiModel):
    """The background-job health card (P0 Task 3): how many jobs ended FAILED inside the last
    ``window_days``. The window rides on the payload so the client can label the card honestly
    ("2 failed jobs (7d)") without hard-coding the number, and the drill-down is the existing
    ``GET /api/v1/jobs?status=FAILED``, which carries each failure's error text."""

    count: int
    window_days: int


class DashboardResponse(ApiModel):
    """The role-based dashboard payload (D-058): every KPI is OPTIONAL — only the KPIs the caller is
    permitted to see are populated (the rest are ``None`` and excluded from the JSON). The CLIENT
    makes ONE call for this whole bundle (PERFORMANCE §4: one screen, one endpoint)."""

    cash_position: MoneyKpi | None = None
    ar_aging: AgingSummary | None = None
    ap_aging: AgingSummary | None = None
    inventory_value: MoneyKpi | None = None
    open_sales_orders: CountValueKpi | None = None
    open_purchase_orders: CountValueKpi | None = None
    otd_percent: OtdKpi | None = None
    wip_value: MoneyKpi | None = None
    failed_jobs: FailedJobsKpi | None = None


# --- Report builder (PLAN 13.2, D-059) ----------------------------------------
# The AD-HOC report request + result. A ReportSpec names a WHITELISTED entity + a subset of its
# whitelisted columns + filters + group-by + aggregations; the builder validates it against the
# registry, builds the ORM select with TYPED BINDS (no SQL injection), runs it tenant-filtered, and
# returns ReportResult. No persistence — define-and-run in one request (D-059, ad-hoc-only v1).


class ReportFilter(ApiModel):
    """One filter on a report (D-059): a whitelisted, filterable ``column``, an ``operator`` from
    the fixed set, and a ``value`` the builder coerces to the column's Python type and BINDS (never
    string-interpolates). ``value`` shape depends on the operator: a scalar for EQ/NE/GT/.../LIKE, a
    list for IN, a [low, high] pair for BETWEEN, a bool for IS_NULL (True → IS NULL)."""

    column: str
    operator: FilterOperator
    value: Any = None


class ReportAggregation(ApiModel):
    """One aggregation on a report (D-059): ``func`` over a whitelisted column (SUM/AVG/MIN/MAX
    require the column be ``is_aggregatable``; COUNT may target any column or omit it via ``*``).
    ``alias`` is the result column name the aggregate lands under (defaults to ``func_column``)."""

    column: str | None = None
    func: Aggregation
    alias: str | None = None


class ReportSpec(ApiModel):
    """An ad-hoc report definition run in one request (D-059). ``entity`` is a registry key;
    ``columns`` is the subset of plain columns to SELECT (used when there is no group-by);
    ``filters`` scope the rows; ``group_by`` (whitelisted groupable columns) + ``aggregations``
    produce a grouped result (when group_by is present the SELECT is the group-by columns + the
    aggregates, not ``columns``). ``limit`` optionally lowers the 10k cap (never raises it)."""

    entity: str
    columns: list[str] = []
    filters: list[ReportFilter] = []
    group_by: list[str] = []
    aggregations: list[ReportAggregation] = []
    limit: int | None = None


class ReportResult(ApiModel):
    """The report grid payload (D-059): ``columns`` is the ordered result column-name list — the
    WIRE names, which are also the keys of each row dict — ``column_labels`` is the matching DISPLAY
    header for each (same length, same order), ``rows`` is a list of {column → JSON-safe value}
    dicts (money/qty as exact strings, dates as ISO), ``row_count`` is len(rows), and ``truncated``
    is True when the result hit the row cap (the UI then offers the streaming CSV export for the
    full set, PERFORMANCE §3).

    WHY BOTH LISTS (#166). The row dicts must stay keyed by the wire name (that is the client's
    lookup key, and duplicate labels would collide), so the human header travels beside them rather
    than replacing them. ``column_labels`` is the SINGLE source both surfaces read: the grid renders
    it as its headers and the CSV export writes it as its header line, so the two can never drift
    apart the way they had (issue #166 — both showed ``sum_total_amount``)."""

    columns: list[str]
    column_labels: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool


# --- The entities catalog (D-059) — so a UI can build the report picker --------


class ReportColumnDescriptor(ApiModel):
    """One whitelisted column as the picker sees it (D-059): the request ``name``, display
    ``label``, wire ``type``, and the per-column capability flags the builder enforces."""

    name: str
    label: str
    type: str
    filterable: bool
    groupable: bool
    is_aggregatable: bool


class ReportEntityDescriptor(ApiModel):
    """One whitelisted reportable entity as the picker sees it (D-059): the ``key`` a spec names,
    its ``label``, and its allowed columns. The entities-list endpoint returns ONLY the entities the
    caller's role permits (each gated by its source permission), so the catalog IS the caller's
    role."""

    key: str
    label: str
    columns: list[ReportColumnDescriptor]


class ReportEntityList(ApiModel):
    """The report-builder entities catalog the UI fetches to build its picker (D-059)."""

    entities: list[ReportEntityDescriptor]
