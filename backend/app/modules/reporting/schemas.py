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
from typing import Annotated

from pydantic import PlainSerializer

from app.core.schemas import ApiModel

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
